import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
from fastkml import kml
from typing import Optional
import os
import re
from google.cloud import storage
import logging
import sys

# --- Logging Config ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)
from google.cloud import storage

# --- Page Config ---
st.set_page_config(
    page_title="Dashboard of Prachinburi District 1",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constants ---
CSV_FILE = "คะแนนเลือกตั้ง_ปราจีนบุรี_เขต1_แบ่งเขต.csv"
KML_FILE = "แผนที่หาเสียงปราจีนบุรี.kml"
COMMENTS_FILE = "comments.csv"
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "prachin-voter-kml-storage")
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "prachin-voter-kml-storage")

# --- Heartbeat Debug ---
import time
st.sidebar.markdown(f"**Server Time:** `{time.strftime('%H:%M:%S')}`")
if 'init_t  ime' not in st.session_state: st.session_state['init_time'] = time.time()
st.sidebar.caption(f"Session Age: {int(time.time() - st.session_state['init_time'])}s")

# --- Data Loading ---

def load_comments() -> list:
    """Loads comments from CSV file."""
    if os.path.exists(COMMENTS_FILE):
        try:
            df = pd.read_csv(COMMENTS_FILE)
            return df.to_dict('records')
        except Exception as e:
            st.error(f"Error loading comments: {e}")
            return []
    return []

def save_comment(comment: dict):
    """Saves a single comment to CSV file."""
    try:
        df_new = pd.DataFrame([comment])
        if os.path.exists(COMMENTS_FILE):
            df_new.to_csv(COMMENTS_FILE, mode='a', header=False, index=False)
        else:
            df_new.to_csv(COMMENTS_FILE, mode='w', header=True, index=False)
    except Exception as e:
        st.error(f"Error saving comment: {e}")

@st.cache_data
def load_csv_data(filepath: str) -> pd.DataFrame:
    """Loads election data from CSV."""
    if not os.path.exists(filepath):
        st.error(f"File not found: {filepath}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(filepath)
        # Verify required columns exist
        required = ['latitude', 'longitude']
        if not all(col in df.columns for col in required):
            st.error(f"CSV missing required columns: {required}")
            return pd.DataFrame()
        return df
    except Exception as e:
        st.error(f"Error loading CSV: {e}")
        return pd.DataFrame()

@st.cache_data
def load_kml_data(filepath: str) -> Optional[gpd.GeoDataFrame]:
    """Loads sub-district polygons from KML."""
    if not os.path.exists(filepath):
        st.error(f"File not found: {filepath}")
        return None
    
    # Try loading with geopandas directly (uses fiona/gdal)
    try:
        # Prioritize specific layers that sound like sub-district boundaries
        target_layers = ['เส้นแบ่งตำบล ปราจีนบุรี', 'Prachin Buri', 'ปราจีนเขต1', 'เขต 1']
        
        # We need to find available layers first to avoid errors
        import fiona
        available_layers = fiona.listlayers(filepath)
        
        selected_layer = None
        for target in target_layers:
            if target in available_layers:
                selected_layer = target
                break
        
        # If no target found, use the first one (default)
        if not selected_layer and available_layers:
            selected_layer = available_layers[0]
            
        if selected_layer:
            gdf = gpd.read_file(filepath, layer=selected_layer)
            # Ensure we have some description field for the tooltip
            if 'Description' not in gdf.columns and 'description' not in gdf.columns:
                 gdf['description'] = gdf['Name'] if 'Name' in gdf.columns else "No details"
            return gdf
            
        return None

    except Exception as e:
        # Fallback manual parsing if GDAL driver issues
        # Using fastkml as requested/fallback
        try:
            with open(filepath, 'rb') as f:
                doc = f.read()
            k = kml.KML()
            k.from_string(doc)
            
            features = []
            # Recursive function to find features
            def extract_features(folder):
                if hasattr(folder, 'features'):
                    for feat in folder.features():
                        if hasattr(feat, 'geometry'):
                            features.append({
                                'geometry': feat.geometry,
                                'name': feat.name,
                                'description': feat.description
                            })
                        extract_features(feat)
            
            extract_features(k)
            
            if features:
                 # Convert to GeoDataFrame
                from shapely.geometry import shape
                # Note: fastkml geometries are already shapely-like or convert easily
                # specific handling might be needed depending on fastkml version
                # But let's assume standard object structure for now or defer to library
                gdf = gpd.GeoDataFrame(features)
                return gdf
            
        except Exception as e2:
            st.error(f"Error loading KML: {e} | Fallback error: {e2}")
            return None


def create_mask_polygon(gdf: gpd.GeoDataFrame) -> Optional[gpd.GeoDataFrame]:
    """Creates a polygon covering the area OUTSIDE the given GeoDataFrame."""
    if gdf is None or gdf.empty:
        return None
    
    # Check if we have polygons. If only lines/points, masking the world excluding them makes no sense (still full world).
    has_polygons = any(geom.geom_type in ('Polygon', 'MultiPolygon') for geom in gdf.geometry)
    if not has_polygons:
        return None

    try:
        from shapely.geometry import box
        
        # Create a large bounding box (covering the world or a sufficient area)
        # User wants "gray out the area that not in the blue polygon".
        world_box = box(-180, -90, 180, 90)
        
        # Merge all districts into one shape
        # shapely 2.0 recommends union_all(), older uses unary_union
        try:
             unified_geom = gdf.geometry.union_all()
        except AttributeError:
             unified_geom = gdf.geometry.unary_union
             
        # Calculate difference: World - Districts
        mask_geom = world_box.difference(unified_geom)
        
        return gpd.GeoDataFrame(geometry=[mask_geom], crs=gdf.crs)
    except Exception as e:
        st.error(f"Error creating mask: {e}")
        return None

def extract_subdistrict_name(row, kml_cols):
    """Extracts sub-district name from KML data."""
    name_col = next((c for c in kml_cols if c.lower() == 'name'), None)
    desc_col = next((c for c in kml_cols if c.lower() == 'description'), None)
    
    t_val = row.get('T_NAME_T', None)
    
    # If not found, try parsing 'description'
    desc_html = str(row[desc_col]) if desc_col else ""
    
    if not t_val and desc_html:
        match = re.search(r"<td>T_NAME_T</td>\s*<td>(.*?)</td>", desc_html, re.IGNORECASE)
        if match:
            t_val = match.group(1).strip()
            
    # Fallback to Name if still not found, or "Unknown"
    if not t_val:
         t_val = row[name_col] if name_col else "Unknown"
         
    return t_val

def extract_amphoe_name(row, kml_cols):
    """Extracts amphoe name from KML data."""
    desc_col = next((c for c in kml_cols if c.lower() == 'description'), None)
    
    a_val = row.get('A_NAME_T', None)
    
    # If not found, try parsing 'description'
    desc_html = str(row[desc_col]) if desc_col else ""
    
    if not a_val and desc_html:
        match = re.search(r"<td>A_NAME_T</td>\s*<td>(.*?)</td>", desc_html, re.IGNORECASE)
        if match:
            a_val = match.group(1).strip()
            
    return a_val if a_val else ""

# --- GCS Helpers ---

def get_gcs_client():
    try:
        from google.auth.exceptions import DefaultCredentialsError
        client = storage.Client()
        return client
    except Exception as e:
        # Don't spam error here, just return None. The caller will handle fallback.
        logger.warning(f"GCS Client not available (likely local mode): {e}")
        return None

def list_gcs_kml_files(bucket_name):
    """Lists all KML files in the bucket."""
    logger.info(f"Listing files in bucket: {bucket_name}")
    client = get_gcs_client()
    if not client: return []
    try:
        bucket = client.bucket(bucket_name)
        # Check if bucket exists (Optional, can be skipped to save latency/perms)
        # if not bucket.exists():
        #    logger.warning(f"Bucket {bucket_name} does not exist or not accessible.")
        #    return []
        blobs = list(bucket.list_blobs()) # Force iteration to check connectivity
        kml_files = [blob.name for blob in blobs if blob.name.lower().endswith('.kml')]
        logger.info(f"Found {len(kml_files)} KML files: {kml_files}")
        return kml_files
    except Exception as e:
        logger.error(f"Error listing GCS files: {e}")
        st.sidebar.error(f"Error listing GCS files: {e}")
        return []

def upload_to_gcs(file_obj, bucket_name, destination_blob_name):
    """Uploads a file object to the bucket OR local temp if GCS unavailable."""
    logger.info(f"Attempting to upload {destination_blob_name}...")
    client = get_gcs_client()
    
    # --- LOCAL FALLBACK ---
    if not client:
        logger.info("GCS unavailable. Using local temporary storage.")
        local_dir = "/tmp/local_uploads"
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        
        local_path = os.path.join(local_dir, destination_blob_name)
        try:
            with open(local_path, "wb") as f:
                f.write(file_obj.getvalue())
            logger.info(f"Saved locally to {local_path}")
            return True
        except Exception as e:
            st.error(f"Local save failed: {e}")
            return False
    # ----------------------

    try:
        bucket = client.bucket(bucket_name)
        
        # Diagnostics proved upload_from_string works, so let's stick to that.
        blob = bucket.blob(destination_blob_name)
        
        # Read bytes from Streamlit UploadedFile
        data = file_obj.getvalue()
        blob.upload_from_string(data, content_type='application/vnd.google-earth.kml+xml')
        
        logger.info(f"Successfully uploaded {destination_blob_name} to GCS (Size: {len(data)} bytes).")
        return True
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")
        st.sidebar.error(f"Error uploading to GCS: {e}")
        return False

def load_kml_from_gcs(bucket_name, blob_name):
    """Downloads KML from GCS (or local temp) to a temp file and queues it for loading."""
    logger.info(f"Loading {blob_name}...")
    client = get_gcs_client()
    
    # --- LOCAL FALLBACK ---
    if not client:
        local_path = os.path.join("/tmp/local_uploads", blob_name)
        if os.path.exists(local_path):
             logger.info(f"Loading from local path: {local_path}")
             return load_kml_data(local_path)
        else:
             st.error(f"Local file not found: {local_path}")
             return None
    # ----------------------

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        temp_filename = f"/tmp/temp_gcs_{blob_name}"
        blob.download_to_filename(temp_filename)
        logger.info(f"Downloaded {blob_name} to {temp_filename}")
        
        gdf = load_kml_data(temp_filename)
        
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        return gdf
    except Exception as e:
        logger.error(f"Error loading {blob_name} from GCS: {e}")
        st.error(f"Error loading {blob_name} from GCS: {e}")
        return None

# --- GCS Helpers ---

@st.cache_resource
def get_gcs_client():
    try:
        return storage.Client()
    except Exception as e:
        st.error(f"Failed to initialize GCS Client: {e}")
        return None

def list_gcs_kml_files(bucket_name):
    """Lists all KML files in the bucket."""
    client = get_gcs_client()
    if not client: return []
    try:
        bucket = client.bucket(bucket_name)
        blobs = bucket.list_blobs()
        return [blob.name for blob in blobs if blob.name.lower().endswith('.kml')]
    except Exception as e:
        st.sidebar.error(f"Error listing GCS files: {e}")
        return []

def upload_to_gcs(file_obj, bucket_name, destination_blob_name):
    """Uploads a file object to the bucket."""
    client = get_gcs_client()
    if not client: return False
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        # Reset pointer just in case
        file_obj.seek(0)
        blob.upload_from_file(file_obj)
        return True
    except Exception as e:
        st.sidebar.error(f"Error uploading to GCS: {e}")
        return False

def load_kml_from_gcs(bucket_name, blob_name):
    """Downloads KML from GCS to a temp file and queues it for loading."""
    client = get_gcs_client()
    if not client: return None
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        temp_filename = f"temp_gcs_{blob_name}"
        blob.download_to_filename(temp_filename)
        
        gdf = load_kml_data(temp_filename)
        
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        return gdf
    except Exception as e:
        st.error(f"Error loading {blob_name} from GCS: {e}")
        return None

def calculate_votes_by_subdistrict(df_election):
    """Aggregates votes by sub-district and determines the winner."""
    if df_election.empty or 'ตำบล' not in df_election.columns:
        return pd.DataFrame()

    numeric_cols = df_election.select_dtypes(include=['number']).columns
    cols_to_drop = ['latitude', 'longitude', 'หน่วย']
    cols_to_sum = [c for c in numeric_cols if c not in cols_to_drop]
    
    df_grouped = df_election.groupby('ตำบล')[cols_to_sum].sum().reset_index()
    df_display = df_grouped.rename(columns=lambda x: x.replace('_แบ่งเขต', ''))
    
    # Calculate Percentage for Turnout
    if 'ผู้มีสิทธิ์' in df_display.columns and 'ผู้มาใช้สิทธิ์' in df_display.columns:
        df_display['เปอร์เซ็นต์ใช้สิทธิ์'] = (df_display['ผู้มาใช้สิทธิ์'] / df_display['ผู้มีสิทธิ์']) * 100

    # Calculate Winner
    party_cols = [
        "ก้าวไกล", "ชาติพัฒนากล้า", "ชาติไทยพัฒนา", "ประชาชาติ", 
        "ประชาธิปัตย์", "พลังประชารัฐ", "ภูมิใจไทย", "รวมไทยสร้างชาติ", 
        "เพื่อไทย", "เสรีรวมไทย", "ไทยสร้างไทย"
    ]
    existing_parties = [p for p in party_cols if p in df_display.columns]
    
    if existing_parties:
        df_display['Winner'] = df_display[existing_parties].idxmax(axis=1)
        
        # Calculate Winner Votes and Percentage
        df_display['Winner_Votes'] = df_display[existing_parties].max(axis=1)
        if 'ผู้มาใช้สิทธิ์' in df_display.columns:
             df_display['Winner_Pct'] = (df_display['Winner_Votes'] / df_display['ผู้มาใช้สิทธิ์'].replace(0, 1)) * 100
        else:
             df_display['Winner_Pct'] = 0

    return df_display

# --- Main App ---

def main():
    st.title("Dashboard of Prachinburi District 1")
    
    # Load Data
    with st.spinner("Loading data..."):
        df_election = load_csv_data(CSV_FILE)
        
        # Always load default districts
        gdf_districts = load_kml_data(KML_FILE)
        
        # --- System Diagnostics (Temporary for Debugging) ---
        # Initialize Run Count
        if 'run_count' not in st.session_state: st.session_state['run_count'] = 0
        st.session_state['run_count'] += 1
        
        with st.sidebar.expander(f"System Diagnostics (Run #{st.session_state['run_count']})", expanded=True):

            st.write(f"**GCS Bucket:** `{GCS_BUCKET_NAME}`")
            
            # Check Client
            client = get_gcs_client()
            if client:
                st.success("GCS Client: Connected")
                
                # Check Bucket
                try:
                    bucket = client.bucket(GCS_BUCKET_NAME)
                    if bucket.exists():
                        st.success(f"Bucket '{GCS_BUCKET_NAME}': Found")
                    else:
                        st.error(f"Bucket '{GCS_BUCKET_NAME}': NOT FOUND")
                except Exception as e:
                    st.error(f"Bucket Check Failed: {e}")
            else:
                st.error("GCS Client: Failed (Check Logs)")
                
            # Check Identity (Detailed)
            if st.button("Check Identity / Test Write"):
                try:
                    import google.auth
                    credentials, project = google.auth.default()
                    
                    st.write(f"**Project:** `{project}`")
                    
                    # Get exact email
                    sa_email = "Unknown"
                    if hasattr(credentials, 'service_account_email'):
                        sa_email = credentials.service_account_email
                    elif hasattr(credentials, 'signer_email'):
                        sa_email = credentials.signer_email
                        
                    st.write(f"**Service Account:** `{sa_email}`")
                    
                    # TEST WRITE
                    if client:
                        bucket = client.bucket(GCS_BUCKET_NAME)
                        blob = bucket.blob("diagnostics_test.txt")
                        blob.upload_from_string("This is a test file from the Prachin Dashboard diagnostics.")
                        st.success(f"✅ Write Test Passed: Uploaded 'diagnostics_test.txt'")
                        
                except Exception as e:
                    st.error(f"❌ Write/Auth Failed: {e}")
                    logger.error(f"Diagnostics failed: {e}")

        # KML uploader
        st.sidebar.markdown("---")
        st.sidebar.header("Data Source")
        
        # Initialize session state for KML layers if not present
        if 'kml_layers' not in st.session_state:
            st.session_state['kml_layers'] = {}
            
            # --- Auto-load from GCS on startup ---
            existing_files = list_gcs_kml_files(GCS_BUCKET_NAME)
            if existing_files:
                with st.spinner(f"Loading {len(existing_files)} KMLs from Cloud Storage..."):
                    for fname in existing_files:
                        if fname not in st.session_state['kml_layers']:
                            gdf_gcs = load_kml_from_gcs(GCS_BUCKET_NAME, fname)
                            if gdf_gcs is not None and not gdf_gcs.empty:
                                st.session_state['kml_layers'][fname] = gdf_gcs

        uploaded_kml = st.sidebar.file_uploader("Upload KML File (Optional)", type=['kml'], key="kml_upload_widget")
        
        if uploaded_kml is not None:
            # 1. Show File Details immediately
            st.sidebar.markdown(f"""
            **File Detected:**
            - Name: `{uploaded_kml.name}`
            - Size: `{uploaded_kml.size / 1024:.2f} KB`
            """)
            
            # 2. Step 1: Upload to Cloud (Safe)
            if st.sidebar.button("1. Upload to Cloud ☁️", key="btn_upload_only"):
                st.sidebar.info("⏳ Uploading bytes to GCS...")
                try:
                    safe_name = uploaded_kml.name.replace(" ", "_")
                    success = upload_to_gcs(uploaded_kml, GCS_BUCKET_NAME, safe_name)
                    
                    if success:
                        st.sidebar.success(f"✅ Upload Success: {safe_name}")
                        
                        # Verify it exists (Check LOCAL or GCS)
                        client = get_gcs_client()
                        if client:
                            bucket = client.bucket(GCS_BUCKET_NAME)
                            blob = bucket.blob(safe_name)
                            exists = blob.exists()
                            loc_msg = f"in GCS bucket {GCS_BUCKET_NAME}"
                        else:
                            # Verify local
                            exists = os.path.exists(os.path.join("/tmp/local_uploads", safe_name))
                            loc_msg = "in local_uploads (Offline Mode)"

                        if exists:
                           st.sidebar.success(f"Verified: File exists {loc_msg}")
                           # Flag state to allow visualization
                           st.session_state['last_uploaded_gcs_path'] = safe_name
                        else:
                           st.sidebar.error(f"❌ Uploaded but file not found {loc_msg}!")
                    else:
                        st.sidebar.error("❌ Upload returned False.")
                except Exception as e:
                    st.sidebar.error(f"Upload Crash: {e}")

            # 3. Step 2: Visualize (Potentially Risky)
            if 'last_uploaded_gcs_path' in st.session_state:
                target_file = st.session_state['last_uploaded_gcs_path']
                st.sidebar.markdown(f"**Ready to View:** `{target_file}`")
                
                if st.sidebar.button(f"2. Visualize {target_file} 🗺️", key="btn_visualize"):
                    st.sidebar.text(f"Downloading & Parsing {target_file}...")
                    try:
                        gdf_new = load_kml_from_gcs(GCS_BUCKET_NAME, target_file)
                        if gdf_new is not None and not gdf_new.empty:
                            st.session_state['kml_layers'][target_file] = gdf_new
                            st.sidebar.success("✅ Layer Added! (Check Layer Controls)")
                            st.rerun()
                        else:
                            st.sidebar.error("❌ Parsing failed (Result is empty/None).")
                    except Exception as e:
                        st.sidebar.error(f"❌ CRITICAL PARSING CRASH: {e}")
                        
        else:
            st.sidebar.caption("Waiting for file selection...")

    # Pre-process Data for Map
    df_votes_by_district = pd.DataFrame()
    if not df_election.empty:
        df_votes_by_district = calculate_votes_by_subdistrict(df_election)

    if gdf_districts is not None and not gdf_districts.empty:
        # Extract sub-district name for merging
        gdf_districts['sub_district_name'] = gdf_districts.apply(lambda row: extract_subdistrict_name(row, gdf_districts.columns), axis=1)
        gdf_districts['amphoe_name'] = gdf_districts.apply(lambda row: extract_amphoe_name(row, gdf_districts.columns), axis=1)
        
        # Merge with election data if available
        if not df_votes_by_district.empty:
            gdf_districts = gdf_districts.merge(
                df_votes_by_district,
                left_on='sub_district_name', 
                right_on='ตำบล', 
                how='left'
            )
            # Fill NaN Winner with "Unknown" and 0 for logic processing but keep NaNs for display where appropriate
            if 'Winner' in gdf_districts.columns:
                 gdf_districts['Winner'] = gdf_districts['Winner'].fillna("Unknown")
            if 'Winner_Pct' in gdf_districts.columns:
                 gdf_districts['Winner_Pct'] = gdf_districts['Winner_Pct'].fillna(0)

    # Create Tabs
    tab_overview, tab_analysis = st.tabs(["Overview", "Analysis Details"])
    
    with tab_overview:
        # Search Feature (Main Area)
        if not df_election.empty and 'ชื่อหน่วยเลือกตั้ง' in df_election.columns:
            all_units = sorted(df_election['ชื่อหน่วยเลือกตั้ง'].astype(str).unique().tolist())
            selected_units = st.multiselect("🔍 Search Election Unit", options=all_units, placeholder="Type to search unit name...")
            
            if selected_units:
                df_election = df_election[df_election['ชื่อหน่วยเลือกตั้ง'].isin(selected_units)]
                st.success(f"Showing {len(df_election)} filtered points.")
                show_points = True # Force show points on map if user is searching

        if gdf_districts is not None and not gdf_districts.empty:
            st.sidebar.success(f"Loaded {len(gdf_districts)} sub-districts")
            
            # Helper to safely get KML columns - for default districts
            kml_cols = gdf_districts.columns
            name_col = next((c for c in kml_cols if c.lower() == 'name'), None)
            desc_col = next((c for c in kml_cols if c.lower() == 'description'), None)
        
            def get_subdistrict_tooltip(row):
                # 1. Title: Sub-district Name
                t_val = row.get('sub_district_name', 'Sub-district')
                a_val = row.get('amphoe_name', '') # Amphoe name from extracted column
                
                header = f"<b>ต.{t_val}</b>"
                if a_val:
                    header += f"<br/>อ.{a_val}"
                header += "<hr style='margin: 5px 0;'/>"

                # 2. Check if we have election data
                if pd.isna(row.get('ตำบล')):
                    return header + "<i>No election data available</i>"

                # 3. Summary Stats
                # Users want to see: Eligible, Turnout, % Turnout
                eligible = row.get('ผู้มีสิทธิ์', 0)
                turnout = row.get('ผู้มาใช้สิทธิ์', 0)
                pct_turnout = row.get('เปอร์เซ็นต์ใช้สิทธิ์', 0)

                stats_html = f"""
                <div style='font-size: 12px; margin-bottom: 8px;'>
                    <b>ผู้มีสิทธิ์:</b> {int(eligible) if pd.notna(eligible) else 0:,}<br/>
                    <b>ผู้มาใช้สิทธิ์:</b> {int(turnout) if pd.notna(turnout) else 0:,} ({pct_turnout:.2f}%)
                </div>
                """

                # 4. Vote Chart (Top 5)
                vote_columns = [
                    "ก้าวไกล", "ชาติพัฒนากล้า", "ชาติไทยพัฒนา", "ประชาชาติ", 
                    "ประชาธิปัตย์", "พลังประชารัฐ", "ภูมิใจไทย", "รวมไทยสร้างชาติ", 
                    "เพื่อไทย", "เสรีรวมไทย", "ไทยสร้างไทย"
                ]
                
                votes = {}
                for col in vote_columns:
                    val = row.get(col, 0)
                    if pd.notna(val):
                        votes[col] = val
                
                max_vote = max(votes.values()) if votes and max(votes.values()) > 0 else 1
                sorted_votes = sorted(votes.items(), key=lambda item: item[1], reverse=True)[:5]
                
                chart_rows = []
                for col, val in sorted_votes:
                    bar_width = (val / max_vote) * 100
                    bar_color = '#4CAF50' 
                    if 'เพื่อไทย' in col: bar_color = '#E60000'
                    if 'ก้าวไกล' in col: bar_color = '#F47920'
                    if 'รวมไทยสร้างชาติ' in col: bar_color = '#4CAF50'
                    if 'พลังประชารัฐ' in col: bar_color = '#4CAF50'
                    if 'ภูมิใจไทย' in col: bar_color = '#00366F'
                    
                    chart_rows.append(f"""
                    <tr>
                        <td style='width: 30%; font-size: 10px; padding-right:5px; white-space:nowrap;'>{col}</td>
                        <td style='width: 15%; font-size: 10px; text-align:right; padding-right:5px;'>{int(val)}</td>
                        <td style='width: 55%;'>
                            <div style='background-color: #ddd; width: 100%; height: 8px; border-radius: 2px;'>
                                <div style='background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 2px;'></div>
                            </div>
                        </td>
                    </tr>
                    """)
                
                chart_table = f"<table style='width:100%; border-collapse: collapse;'>{''.join(chart_rows)}</table>"
                
                return header + stats_html + chart_table
        
            gdf_districts['tooltip_html'] = gdf_districts.apply(get_subdistrict_tooltip, axis=1)

        else:
            st.sidebar.warning("Failed to load default KML polygons")

        if st.session_state['kml_layers']:
             total_features = sum(len(gdf) for gdf in st.session_state['kml_layers'].values())
             st.sidebar.success(f"Loaded {len(st.session_state['kml_layers'])} files ({total_features} features)")

        if not df_election.empty:
             st.sidebar.success(f"Loaded {len(df_election)} points from CSV")

         
             # Prepare Election Tooltip HTML
             def get_election_html(row):
                # General Info Columns
                info_columns = [
                    "หน่วย", "ผู้มีสิทธิ์_แบ่งเขต", "ผู้มาใช้สิทธิ์_แบ่งเขต", "เปอร์เซ็นต์ใช้สิทธิ์_แบ่งเขต",
                    "บัตรเสีย_แบ่งเขต", "ไม่เลือกผู้ใด_แบ่งเขต"
                ]
            
                # Vote Columns for Chart
                vote_columns = [
                    "ก้าวไกล_แบ่งเขต", "ชาติพัฒนากล้า_แบ่งเขต", "ชาติไทยพัฒนา_แบ่งเขต", "ประชาชาติ_แบ่งเขต", 
                    "ประชาธิปัตย์_แบ่งเขต", "พลังประชารัฐ_แบ่งเขต", "ภูมิใจไทย_แบ่งเขต", "รวมไทยสร้างชาติ_แบ่งเขต", 
                    "เพื่อไทย_แบ่งเขต", "เสรีรวมไทย_แบ่งเขต", "ไทยสร้างไทย_แบ่งเขต"
                ]
            
                unit_name = row.get('ชื่อหน่วยเลือกตั้ง', 'Election Unit')
                header = f"<b>{unit_name}</b><hr style='margin: 5px 0;'/>"
            
                # 1. Info Stats Table
                info_rows = []
                for col in info_columns:
                    val = row.get(col, "-")
                    info_rows.append(f"<tr><td style='padding-right: 10px; font-weight: bold;'>{col}:</td><td>{val}</td></tr>")
            
                info_table = f"<table style='width:100%; border-collapse: collapse; font-size: 12px; margin-bottom: 10px;'>{''.join(info_rows)}</table>"
            
                # 2. Vote Chart
                # Parse votes to find max for scaling
                votes = {}
                max_vote = 1
                for col in vote_columns:
                    try:
                        val = float(row.get(col, 0))
                    except:
                        val = 0
                    votes[col] = val
            
                if votes:
                    max_vote = max(votes.values()) if max(votes.values()) > 0 else 1
            
                # Sort votes by value descending
                sorted_votes = sorted(votes.items(), key=lambda item: item[1], reverse=True)
            
                # Limit to top 5 (User Request)
                sorted_votes = sorted_votes[:5]
            
                chart_rows = []
                for col, val in sorted_votes:
                    # Simple cleaning of column name for display (remove '_แบ่งเขต')
                    display_name = col.replace('_แบ่งเขต', '')
                
                    bar_width = (val / max_vote) * 100
                    bar_color = '#4CAF50' # Default Green
                    # Optional: Custom colors for known parties
                    if 'เพื่อไทย' in col: bar_color = '#E60000' # Red
                    if 'ก้าวไกล' in col: bar_color = '#F47920' # Orange
                    if 'รวมไทยสร้างชาติ' in col: bar_color = '#4CAF50' # Green (Requested)
                    if 'พลังประชารัฐ' in col: bar_color = '#4CAF50' # Green (Requested)
                    if 'ภูมิใจไทย' in col: bar_color = '#00366F' # Dark Blue
                
                    chart_rows.append(f"""
                    <tr>
                        <td style='width: 30%; font-size: 10px; padding-right:5px; white-space:nowrap;'>{display_name}</td>
                        <td style='width: 15%; font-size: 10px; text-align:right; padding-right:5px;'>{int(val)}</td>
                        <td style='width: 55%;'>
                            <div style='background-color: #ddd; width: 100%; height: 8px; border-radius: 2px;'>
                                <div style='background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 2px;'></div>
                            </div>
                        </td>
                    </tr>
                    """)
            
                chart_header = "<div style='font-size: 12px; font-weight: bold; margin-bottom: 2px;'>Vote Counts</div>"
                chart_table = f"<table style='width:100%; border-collapse: collapse;'>{''.join(chart_rows)}</table>"
            
                return header + info_table + chart_header + chart_table
            
             df_election['tooltip_html'] = df_election.apply(get_election_html, axis=1)
    
        # Initialize Session State for Comments from File
        if 'comments' not in st.session_state:
            st.session_state['comments'] = load_comments()

        # Sidebar Controls
        st.sidebar.header("Layer Controls")
        show_districts = st.sidebar.checkbox("Show Sub-districts (KML)", value=True)
        show_winner = st.sidebar.checkbox("Show Winner (Sub-district)", value=False)
        
        # Dynamic Controls for Uploaded Layers
        active_uploaded_layers = []
        if st.session_state['kml_layers']:
            st.sidebar.markdown("**Uploaded Layers:**")
            for name in st.session_state['kml_layers'].keys():
                if st.sidebar.checkbox(f"Show {name}", value=True):
                    active_uploaded_layers.append(name)
            
            if st.sidebar.button("Clear All Uploaded Layers"):
                st.session_state['kml_layers'] = {}
                st.rerun()
        
        show_points = st.sidebar.checkbox("Show Election Points (CSV)", value=True)
    
        st.sidebar.markdown("---")
        st.sidebar.header("Map Style")
        map_style_selection = st.sidebar.radio(
            "Select Base Map",
            options=["Satellite", "Default (Light)", "Terrain (ภูมิประเทศ)"],
            index=1
        )
        

    
        # Map Style Mapping
        map_styles = {
            "Satellite": "mapbox://styles/mapbox/satellite-v9",
            "Default (Light)": "mapbox://styles/mapbox/light-v9",
            "Terrain (ภูมิประเทศ)": "mapbox://styles/mapbox/outdoors-v12"
        }
        selected_map_style = map_styles.get(map_style_selection, "mapbox://styles/mapbox/light-v9")
    
        # Prepare Pydeck Layers
        layers = []
    
        if show_districts and gdf_districts is not None:
            # 1. Mask Layer (Gray out outside)
            gdf_mask = create_mask_polygon(gdf_districts)
            if gdf_mask is not None:
                 layer_mask = pdk.Layer(
                    "GeoJsonLayer",
                    gdf_mask,
                    opacity=0.5,
                    stroked=False,
                    filled=True,
                    get_fill_color=[128, 128, 128, 100], # Gray, semi-transparent
                    pickable=False,
                )
                 layers.append(layer_mask)

            # 2. Polygon Layer - Blue Lines Style (Requested)
            layer_districts = pdk.Layer(
                "GeoJsonLayer",
                gdf_districts,
                opacity=1.0,
                stroked=True,
                filled=True, 
                get_fill_color=[0, 0, 0, 0], 
                get_line_color=[0, 0, 255, 255], # Blue lines
                get_line_width=30,
                lineWidthMinPixels=2, # Ensure visibility at high zoom levels
                pickable=True,
                auto_highlight=True,
                wireframe=True,
                highlight_color=[0, 0, 255, 128], # Blue highlight
            )
            layers.append(layer_districts)

        # 2b. Uploaded Layers (Stacked)
        for name in active_uploaded_layers:
             gdf_layer = st.session_state['kml_layers'].get(name)
             if gdf_layer is not None:
                 layer_uploaded = pdk.Layer(
                    "GeoJsonLayer",
                    gdf_layer,
                    id=f"layer-{name}", # Unique ID for pydeck
                    opacity=1.0,
                    stroked=True,
                    filled=False, 
                    get_line_color=[255, 80, 0, 255], # Deep Orange
                    get_line_width=30,
                    lineWidthMinPixels=2,
                    pickable=False,
                )
                 layers.append(layer_uploaded)

        if show_winner and gdf_districts is not None and 'Winner' in gdf_districts.columns:
            # 3. Winner Layer
            # Define Color Function logic for Pydeck
            # We need to map Winner string to Color [R, G, B, A]
            
            def get_winner_color(row):
                winner = row.get('Winner', '')
                pct = row.get('Winner_Pct', 0)
                
                # Determine Alpha based on Percentage
                if pct > 45:
                    alpha = 200 # High intensity
                elif pct >= 30:
                    alpha = 120 # Medium intensity
                else:
                    alpha = 60  # Low intensity

                if winner == 'ภูมิใจไทย':
                    return [0, 0, 255, alpha] 
                elif winner == 'ก้าวไกล':
                    return [255, 165, 0, alpha]
                elif winner == 'เพื่อไทย':
                    return [255, 0, 0, alpha]
                else:
                    return [200, 200, 200, 50]
            
            gdf_districts['winner_color'] = gdf_districts.apply(get_winner_color, axis=1)

            layer_winner = pdk.Layer(
                "GeoJsonLayer",
                gdf_districts,
                opacity=1.0,
                stroked=True,
                filled=True,
                get_fill_color="winner_color",
                get_line_color=[255, 255, 255, 100],
                get_line_width=10,
                pickable=True,
                auto_highlight=True,
                highlight_color=[0, 255, 255, 100],
            )
            layers.append(layer_winner)

        if show_points and not df_election.empty:
            # Scatterplot Layer
            layer_points = pdk.Layer(
                "ScatterplotLayer",
                df_election,
                get_position=['longitude', 'latitude'],
                get_color=[255, 65, 54, 200], # Redish
                get_radius=100,
                pickable=True,
                auto_highlight=True,
            )
            layers.append(layer_points)
        
        # Comments Layer
        if st.session_state['comments']:
            df_comments = pd.DataFrame(st.session_state['comments'])
        
            # Add tooltip for comments
            df_comments['tooltip_html'] = df_comments.apply(lambda row: f"<b>Comment</b><br/>{row.get('text', '')}", axis=1)

            layer_comments = pdk.Layer(
                "ScatterplotLayer", 
                df_comments,
                get_position=['longitude', 'latitude'],
                get_fill_color=[0, 255, 0, 255], # Green
                get_radius=300, 
                pickable=True,
                auto_highlight=True,
            )
            layers.append(layer_comments)
        
        # Map State
        # Center map on data
        if not df_election.empty:
            # Dynamic Zoom Logic
            # If we are validly filtered to a single point (or very few), zoom in close.
            # If we show all data (len > 100 usually), zoom out.
            
            row_count = len(df_election)
            
            # Default zoom
            zoom_level = 10
            
            if row_count == 1:
                zoom_level = 15
            elif row_count < 5:
                zoom_level = 13
            
            initial_view_state = pdk.ViewState(
                latitude=df_election['latitude'].mean(),
                longitude=df_election['longitude'].mean(),
                zoom=zoom_level,
                pitch=0,
            )
        else:
            initial_view_state = pdk.ViewState( latitude=14.0, longitude=101.5, zoom=10 ) 

        # Tooltip
        # We use the pre-calculated 'tooltip_html' column from dataframes
        tooltip = {
            "html": "{tooltip_html}", 
            "style": {"backgroundColor": "steelblue", "color": "white", "maxWidth": "300px"}
        }
    
        # Render Map - Using Selected Style
        r = pdk.Deck(
            layers=layers,
            initial_view_state=initial_view_state,
            map_style=selected_map_style, 
            tooltip=tooltip
        )
    
        st.pydeck_chart(r)
        
        # Legend (Only if Winner layer is active)
        if show_winner:
            st.markdown("""
            **Winning Percentage Intensity:**
            *   **> 45%**: High Intensity
            *   **30% - 45%**: Medium Intensity
            *   **< 30%**: Low Intensity
            """)
    
        # Comments / Annotation Section
        st.markdown("---")
        st.header("Campaign Comments")
        st.markdown("Add a comment to a specific location directly to `comments.csv`.")
    
        # Form to add comment
        with st.form("comment_form"):
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                 c_lat = st.number_input("Latitude", value=initial_view_state.latitude, format="%.6f")
            with c_col2:
                 c_lon = st.number_input("Longitude", value=initial_view_state.longitude, format="%.6f")
        
            c_text = st.text_area("Comment Text")
            c_submit = st.form_submit_button("Add Comment")
        
            if c_submit:
                if c_text:
                    new_comment = {
                        "latitude": c_lat,
                        "longitude": c_lon,
                        "text": c_text,
                        "ชื่อหน่วยเลือกตั้ง": "Comment: " + c_text[:20] # For tooltip compat
                    }
                    # Save to session
                    st.session_state['comments'].append(new_comment)
                    # Save to file
                    save_comment(new_comment)
                
                    st.success("Comment added and saved to file!")
                    st.rerun()
                else:
                    st.warning("Please enter some text.")
            
        # Display Comments
        if st.session_state['comments']:
            st.subheader("Existing Comments")
            st.dataframe(pd.DataFrame(st.session_state['comments'])[['latitude', 'longitude', 'text']])

    with tab_analysis:
        st.header("Analysis Details: Aggregated by Sub-district (ตำบล)")
        
        if not df_election.empty:
            # Group by 'ตำบล' and sum numeric columns
            # We filter for only numeric columns for summation to avoid errors
            numeric_cols = df_election.select_dtypes(include=['number']).columns
            # Ensure 'ตำบล' is preserved or we verify it exists
            if 'ตำบล' in df_election.columns:
                # Group by 'ตำบล'
                # list(numeric_cols) includes latitude/longitude which we might not want to sum, but for "all data" maybe user wants specific cols.
                # Usually we sum votes and eligible voters.
                # Let's drop lat/long/unit number from sum if they exist, as summing them is meaningless
                cols_to_drop = ['latitude', 'longitude', 'หน่วย']
                cols_to_sum = [c for c in numeric_cols if c not in cols_to_drop]
                
                df_grouped = df_election.groupby('ตำบล')[cols_to_sum].sum().reset_index()
                
                # Optional: Clean up column names for display (remove _แบ่งเขต)
                df_display = df_grouped.rename(columns=lambda x: x.replace('_แบ่งเขต', ''))

                # Add percentage column
                if 'ผู้มีสิทธิ์' in df_display.columns and 'ผู้มาใช้สิทธิ์' in df_display.columns:
                    df_display['เปอร์เซ็นต์ใช้สิทธิ์'] = (df_display['ผู้มาใช้สิทธิ์'] / df_display['ผู้มีสิทธิ์']) * 100

                # Calculate Winner
                party_cols = [
                    "ก้าวไกล", "ชาติพัฒนากล้า", "ชาติไทยพัฒนา", "ประชาชาติ", 
                    "ประชาธิปัตย์", "พลังประชารัฐ", "ภูมิใจไทย", "รวมไทยสร้างชาติ", 
                    "เพื่อไทย", "เสรีรวมไทย", "ไทยสร้างไทย"
                ]
                # Filter to only existing columns to be safe
                existing_parties = [p for p in party_cols if p in df_display.columns]
                
                if existing_parties:
                    df_display['Winner'] = df_display[existing_parties].idxmax(axis=1)
                    
                    # Calculate Winner Percentage
                    winner_votes = df_display[existing_parties].max(axis=1)
                    if 'ผู้มาใช้สิทธิ์' in df_display.columns:
                         df_display['Winner Percentage'] = (winner_votes / df_display['ผู้มาใช้สิทธิ์'].replace(0, 1)) * 100

                st.dataframe(df_display, use_container_width=True)
                
                # Show some metrics
                total_voters = df_display['ผู้มีสิทธิ์'].sum() if 'ผู้มีสิทธิ์' in df_display.columns else 0
                total_turnout = df_display['ผู้มาใช้สิทธิ์'].sum() if 'ผู้มาใช้สิทธิ์' in df_display.columns else 0
                
                # Display generic metrics if columns match expectations
                if total_voters > 0:
                    st.metric("Total Eligible Voters", f"{total_voters:,}")
                    st.metric("Total Turnout", f"{total_turnout:,}")

            else:
                st.error("Column 'ตำบล' not found in data.")
        else:
            st.info("No election data loaded.")

if __name__ == "__main__":
    main()
