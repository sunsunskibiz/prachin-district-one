import streamlit as st
import pandas as pd
import geopandas as gpd
from fastkml import kml
from typing import Optional
import os
import io
from .constants import COMMENTS_FILE, GCS_BUCKET_NAME, COLORS_FILE
import json
# Note: Circular import risk if we import load_kml_from_gcs here if it imports this.
# Avoiding circular import by importing inside function or using separate module structure correctly.
# Ideally gcs_utils should not import data_utils if data_utils uses gcs_utils.
# Refactoring: gcs_utils currently imports load_kml_data from data_utils.
# So data_utils CANNOT import gcs_utils directly at top level if not careful.
# We will use lazy imports inside the function.

def load_comments() -> list:
    """Loads comments from CSV file (First GCS, then Local fallback)."""
    # Try GCS First (Sync)
    from .gcs_utils import download_text_from_gcs
    csv_text = download_text_from_gcs(GCS_BUCKET_NAME, f"shared/{COMMENTS_FILE}")
    
    if csv_text:
        try:
            df = pd.read_csv(io.StringIO(csv_text))
            # Save to local for fallback/cache
            df.to_csv(COMMENTS_FILE, index=False)
            return df.to_dict('records')
        except Exception as e:
            st.error(f"Error parsing GCS comments: {e}")

    # Fallback to local
    if os.path.exists(COMMENTS_FILE):
        try:
            df = pd.read_csv(COMMENTS_FILE)
            return df.to_dict('records')
        except Exception as e:
            return []
    return []

def save_comment(comment: dict):
    """Saves a single comment to CSV file (Local + GCS Sync)."""
    try:
        # Load current state to append correctly (safer for schema changes)
        df_new = pd.DataFrame([comment])
        
        if os.path.exists(COMMENTS_FILE):
            try:
                df_existing = pd.read_csv(COMMENTS_FILE)
                # Concatenate to handle new columns automatically (fills missing with NaN)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            except Exception as e:
                # If read fails (e.g. empty file), just use new
                 df_combined = df_new
        else:
            df_combined = df_new
            
        # Save Local
        df_combined.to_csv(COMMENTS_FILE, index=False)
            
        # Sync to GCS: Read full file and upload
        with open(COMMENTS_FILE, 'r') as f:
            full_csv_content = f.read()
        
        from .gcs_utils import upload_text_to_gcs
        upload_text_to_gcs(full_csv_content, GCS_BUCKET_NAME, f"shared/{COMMENTS_FILE}")
            
    except Exception as e:
        st.error(f"Error saving comment: {e}")

def delete_comment(comment_to_delete: dict):
    """Deletes a single comment from CSV file (Local + GCS Sync)."""
    try:
        if not os.path.exists(COMMENTS_FILE):
            return

        df = pd.read_csv(COMMENTS_FILE)
        
        # Filter based on lat/lon/text/timestamp to find the row to remove
        # We need to be careful about floating point comparison for lat/lon
        # But usually exact match from the file load works if we use the string representation or tolerance
        # Ideally, we should have a unique ID, but for now we match fields.
        
        # Create a mask for matching
        mask = (
            (df['latitude'] == comment_to_delete['latitude']) & 
            (df['longitude'] == comment_to_delete['longitude']) & 
            (df['text'] == comment_to_delete['text'])
        )
        
        # If timestamp exists in both, use it too
        if 'timestamp' in comment_to_delete and 'timestamp' in df.columns:
             # handle NaN in file vs string in dict
             target_ts = comment_to_delete['timestamp']
             # Ensure string comparison
             mask = mask & (df['timestamp'].fillna('').astype(str) == str(target_ts))

        # Keep rows that match the mask FALSE (i.e. keep rows that are NOT the comment to delete)
        # However, we only want to delete ONE match if duplicates exist? 
        # Or all matches? Let's delete all matches of this specific comment content.
        df_new = df[~mask]
        
        df_new.to_csv(COMMENTS_FILE, index=False)
            
        # Sync to GCS
        with open(COMMENTS_FILE, 'r') as f:
            full_csv_content = f.read()
            
        from .gcs_utils import upload_text_to_gcs
        upload_text_to_gcs(full_csv_content, GCS_BUCKET_NAME, f"shared/{COMMENTS_FILE}")
            
    except Exception as e:
        st.error(f"Error deleting comment: {e}")


def load_subdistrict_colors() -> dict:
    """Loads subdistrict colors from JSON file (First GCS, then Local fallback)."""
    # Try GCS First (Sync)
    from .gcs_utils import download_text_from_gcs
    try:
        json_text = download_text_from_gcs(GCS_BUCKET_NAME, f"shared/{COLORS_FILE}")
        if json_text:
            data = json.loads(json_text)
            # Save to local for fallback/cache
            with open(COLORS_FILE, 'w') as f:
                json.dump(data, f)
            return data
    except Exception as e:
        # st.warning(f"Note: Could not load colors from GCS: {e}") 
        pass

    # Fallback to local
    if os.path.exists(COLORS_FILE):
        try:
            with open(COLORS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            return {}
    return {}

def save_subdistrict_color(sub_district_name: str, color_key: str):
    """Saves a subdistrict color assignment (Local + GCS Sync)."""
    try:
        # Load current state
        if os.path.exists(COLORS_FILE):
             with open(COLORS_FILE, 'r') as f:
                try:
                    data = json.load(f)
                except:
                    data = {}
        else:
            data = {}
        
        # Update
        data[sub_district_name] = color_key
        
        # Save Local
        with open(COLORS_FILE, 'w') as f:
            json.dump(data, f)
            
        # Sync to GCS
        json_content = json.dumps(data)
        from .gcs_utils import upload_text_to_gcs
        upload_text_to_gcs(json_content, GCS_BUCKET_NAME, f"shared/{COLORS_FILE}")
            
    except Exception as e:
        st.error(f"Error saving color: {e}")

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
        # st.error(f"File not found: {filepath}") # Suppress to allow silent checks by other utils
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
                gdf = gpd.GeoDataFrame(features)
                return gdf
            
        except Exception as e2:
            st.error(f"Error loading KML: {e} | Fallback error: {e2}")
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

@st.cache_data
def load_campaign_pins() -> Optional[gpd.GeoDataFrame]:
    """Loads and merges campaign pins from multiple JSON files."""
    from .constants import CAMPAIGN_PINS_FILES
    
    gdfs = []
    
    for filepath in CAMPAIGN_PINS_FILES:
        if os.path.exists(filepath):
            try:
                gdf = gpd.read_file(filepath)
                if not gdf.empty:
                    gdfs.append(gdf)
            except Exception as e:
                st.warning(f"Error loading {filepath}: {e}")
    
    if not gdfs:
        return None
        
    try:
        # Merge all dataframes
        gdf_merged = pd.concat(gdfs, ignore_index=True)
        
        # Ensure 'name' exists for tooltip
        if 'name' not in gdf_merged.columns:
             gdf_merged['name'] = "Campaign Pin"
        else:
             # Fill missing names
             gdf_merged['name'] = gdf_merged['name'].fillna("Campaign Pin")
             
        return gdf_merged
    except Exception as e:
        st.error(f"Error merging campaign pins: {e}")
        return None
