import streamlit as st
import pandas as pd
import pydeck as pdk
import time
import logging
import sys
import os
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

# Import from new utils
from utils.constants import CSV_FILE, KML_FILE, GCS_BUCKET_NAME
from utils.geo_utils import create_mask_polygon, extract_subdistrict_name, extract_amphoe_name, process_path_overlaps
from utils.data_utils import load_comments, save_comment, load_csv_data, load_kml_data, calculate_votes_by_subdistrict, load_campaign_pins, load_subdistrict_colors, save_subdistrict_color
from utils.gcs_utils import list_gcs_kml_files, upload_to_gcs, load_kml_from_gcs, get_gcs_client

# --- Logging Config ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

# --- Page Config ---
st.set_page_config(
    page_title="Dashboard of Prachinburi District 1",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Authentication Setup ---
def setup_auth():
    with open('auth_config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        # preauthorized=config['preauthorized'] 
    )
    return authenticator, config

def main():
    logger.info("--- Main App Run ---")
    # Auth Check
    authenticator, config = setup_auth()
    try:
        authenticator.login()
    except Exception as e:
        st.error(e)

    if st.session_state["authentication_status"]:
        username = st.session_state["username"]
        
        # --- LOGGED IN CONTENT ---
        with st.sidebar:
            st.write(f"USER: **{st.session_state['name']}**")
            authenticator.logout('Logout', 'main')
            st.divider()
        
        _main_app_logic(username)

    elif st.session_state["authentication_status"] is False:
        st.error('Username/password is incorrect')
    elif st.session_state["authentication_status"] is None:
        st.warning('Please enter your username and password')


def _main_app_logic(username):
    st.title("Dashboard of Prachinburi District 1")
    
    # --- Heartbeat Debug ---
    # st.sidebar.markdown(f"**Server Time:** `{time.strftime('%H:%M:%S')}`")
    
    # Load Data
    with st.spinner("Loading data..."):
        df_election = load_csv_data(CSV_FILE).copy()
        
        # Always load default districts
        gdf_districts_data = load_kml_data(KML_FILE)
        gdf_districts = gdf_districts_data.copy() if gdf_districts_data is not None else None
        
        # Load Campaign Pins
        gdf_campaign_pins = load_campaign_pins()
        if gdf_campaign_pins is not None and not gdf_campaign_pins.empty:
            gdf_campaign_pins['tooltip_html'] = gdf_campaign_pins['name'].apply(lambda x: f"<b>{x}</b>")
            
        # Load Sub-district Colors
        subdistrict_colors = load_subdistrict_colors()

        # KML uploader
        st.sidebar.header("Data Source")
        
        # Initialize session state for KML layers if not present
        if 'kml_layers' not in st.session_state:
            st.session_state['kml_layers'] = {}
            
            # --- Auto-load from GCS on startup (User specific + maybe shared?) ---
            # For now, let's load USER files
            user_prefix = f"uploads/{username}/"
            existing_files = list_gcs_kml_files(GCS_BUCKET_NAME, prefix=user_prefix)
            
            if existing_files:
                # Limit to avoid overloading if many files
                with st.spinner(f"Loading {len(existing_files)} KMLs..."):
                    for fname in existing_files:
                        if fname not in st.session_state['kml_layers']:
                            gdf_gcs = load_kml_from_gcs(GCS_BUCKET_NAME, fname)
                            if gdf_gcs is not None and not gdf_gcs.empty:
                                # Key by filename relative (cleaner UI) or full path?
                                # Let's use full path for uniqueness in backend, but maybe display cleaner name
                                st.session_state['kml_layers'][fname] = gdf_gcs

        uploaded_kml = st.sidebar.file_uploader("Upload KML File (Optional)", type=['kml'], key="kml_upload_widget")
        
        if uploaded_kml is not None:
             # Auto-Process Logic
             file_id = f"{uploaded_kml.name}_{uploaded_kml.size}"
             
             if file_id not in st.session_state.get('processed_uploads', []):
                 if 'processed_uploads' not in st.session_state: st.session_state['processed_uploads'] = []
                 
                 st.sidebar.info(f"Processing {uploaded_kml.name}...")
                 
                 # Name Spacing: uploads/{username}/{filename}
                 safe_filename = uploaded_kml.name.replace(" ", "_")
                 destination_path = f"uploads/{username}/{safe_filename}"
                 
                 # 1. Determine Environment (Cloud vs Local)
                 client = get_gcs_client()
                 
                 if client:
                     # --- CLOUD MODE (GCS) ---
                     success = upload_to_gcs(uploaded_kml, GCS_BUCKET_NAME, destination_path)
                     if success:
                         st.sidebar.success(f"☁️ Uploaded to GCS!")
                         # Auto-Visualize
                         try:
                             gdf_new = load_kml_from_gcs(GCS_BUCKET_NAME, destination_path)
                             if gdf_new is not None and not gdf_new.empty:
                                 st.session_state['kml_layers'][destination_path] = gdf_new
                                 st.success(f"✅ Visualized: {safe_filename}")
                                 st.session_state['processed_uploads'].append(file_id)
                                 st.rerun()
                             else:
                                 st.sidebar.error("Parsed KML is empty.")
                         except Exception as e:
                             st.sidebar.error(f"Visualization Failed: {e}")
                     else:
                         st.sidebar.error("GCS Upload Failed.")
                         
                 else:
                     # --- LOCAL MODE (Session Only) ---
                     # For local, we just ignore the folder structure for simplicity or mock it
                     try:
                         temp_path = os.path.join("/tmp", safe_filename)
                         with open(temp_path, "wb") as f:
                             f.write(uploaded_kml.getbuffer())
                             
                         st.sidebar.info("Parsing locally...")
                         gdf_new = load_kml_data(temp_path)
                         if gdf_new is not None and not gdf_new.empty:
                             st.session_state['kml_layers'][safe_filename] = gdf_new # No prefix for local
                             st.sidebar.success(f"🏠 Loaded locally: {safe_filename}")
                             st.session_state['processed_uploads'].append(file_id)
                             st.rerun()
                         else:
                             st.sidebar.error("Local parse failed.")
                     except Exception as e:
                         st.sidebar.error(f"Local Processing Error: {e}")

             else:
                 st.sidebar.success(f"✅ Loaded: {uploaded_kml.name}")
                 st.sidebar.caption("File already processed.")


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
            # Helper to safely get KML columns - for default districts
            kml_cols = gdf_districts.columns
        
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
        show_districts = st.sidebar.checkbox("แสดงเขตตำบล", value=True)
        show_comments = st.sidebar.checkbox("Comments", value=True)
        show_winner = st.sidebar.checkbox("แสดงเขตผู้ชนะ", value=False)
        show_points = st.sidebar.checkbox("หน่วยเลือกตั้ง", value=True)
        show_campaign_pins = st.sidebar.checkbox("จุดติดป้าย", value=False)
        
        st.sidebar.markdown("**Color Highlights:**")
        show_color_orange = st.sidebar.checkbox("Fill Orange (Som)", value=True)
        show_color_green = st.sidebar.checkbox("Fill Low-Green", value=True)
        show_color_yellow = st.sidebar.checkbox("Fill Low-Yellow", value=True)
        show_color_blue = st.sidebar.checkbox("Fill Low-Blue", value=True)
        
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
                    id="layer_mask",
                    opacity=0.5,
                    stroked=False,
                    filled=True,
                    get_fill_color=[128, 128, 128, 100], # Gray, semi-transparent
                    pickable=False,
                )
                 layers.append(layer_mask)

            # 2. Polygon Layer - Blue Lines Style (Requested) + Color Fill Feature
            # Assign colors to GDF based on subdistrict_colors dict
            def get_district_fill_color(row):
                 # Get standard name
                 s_name = row.get('sub_district_name', '')
                 assigned_color = subdistrict_colors.get(s_name, None)
                 
                 base_alpha = 140
                 
                 if assigned_color == 'orange' and show_color_orange:
                     return [255, 165, 0, base_alpha]
                 elif assigned_color == 'green' and show_color_green:
                     return [144, 238, 144, base_alpha] # Light Green
                 elif assigned_color == 'yellow' and show_color_yellow:
                     return [255, 255, 224, base_alpha] # Light Yellow
                 elif assigned_color == 'blue' and show_color_blue:
                     return [173, 216, 230, base_alpha] # Light Blue
                 
                 return [0, 0, 0, 0] # Transparent

            gdf_districts['const_fill_color'] = gdf_districts.apply(get_district_fill_color, axis=1)

            layer_districts = pdk.Layer(
                "GeoJsonLayer",
                gdf_districts,
                id="layer_districts",
                opacity=1.0,
                stroked=True,
                filled=True, 
                get_fill_color="const_fill_color", 
                get_line_color=[0, 0, 255, 255], # Blue lines
                get_line_width=30,
                lineWidthMinPixels=2, # Ensure visibility at high zoom levels
                pickable=True, # Make sure it's pickable for color assignment
                auto_highlight=True, # Highlight on hover
                wireframe=True,
                highlight_color=[0, 0, 255, 128], # Blue highlight
            )
            layers.append(layer_districts)

        # 2b. Uploaded Layers (Merged & Colored by Overlap)
        if active_uploaded_layers:
            # Prepare list of layers for the cached function
            layers_to_process = []
            for name in active_uploaded_layers:
                layer = st.session_state['kml_layers'].get(name)
                if layer is not None:
                    layers_to_process.append(layer)

            if layers_to_process:
                # Call cached function
                with st.spinner("Processing overlaps..."):
                    gdf_merged = process_path_overlaps(layers_to_process, active_uploaded_layers)
            
                if gdf_merged is not None and not gdf_merged.empty:
                    layer_uploaded = pdk.Layer(
                        "GeoJsonLayer",
                        gdf_merged,
                        id="layer-uploaded-merged",
                        opacity=1.0,
                        stroked=True,
                        filled=False, 
                        get_line_color="color", # Data-driven color from process_path_overlaps
                        get_line_width=30,
                        lineWidthMinPixels=2,
                        pickable=False,
                    )
                    layers.append(layer_uploaded)

        if show_winner and gdf_districts is not None and 'Winner' in gdf_districts.columns:
            # 3. Winner Layer
            # Define Color Function logic for Pydeck
            def get_winner_color(row):
                winner = row.get('Winner', '')
                pct = row.get('Winner_Pct', 0)
                
                # Determine Alpha based on Percentage
                try:
                    pct_val = float(pct)
                except (ValueError, TypeError):
                    pct_val = 0

                if pct_val > 45:
                    alpha = 200 # High intensity
                elif pct_val >= 30:
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
                id="layer_winner",
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
                id="layer_points",
                get_position=['longitude', 'latitude'],
                get_color=[255, 65, 54, 200], # Redish
                get_radius=100,
                pickable=True,
                auto_highlight=True,
            )
            layers.append(layer_points)
            
        if show_campaign_pins and gdf_campaign_pins is not None:
             # Campaign Pins Layer - Square Shape (using ColumnLayer with 4 sides)
             import math
             layer_campaign = pdk.Layer(
                "ColumnLayer",
                gdf_campaign_pins,
                id="layer_campaign_pins",
                get_position=['geometry.coordinates[0]', 'geometry.coordinates[1]'],
                get_fill_color=[128, 0, 128, 200], # Purple
                get_line_color=[255, 255, 255, 255],
                get_line_width=2,
                radius=100,
                disk_resolution=4,
                get_angle=math.pi / 4, # Rotate 45 deg to align as square
                get_elevation=0,
                extruded=False,
                stroked=True,
                pickable=True,
                auto_highlight=True,
            )
             layers.append(layer_campaign)
        
        # Comments Layer (Aggregated for Timeline)
        if show_comments and st.session_state['comments']:
            # Aggregate comments by location for Tooltip Timeline
            df_raw_comments = pd.DataFrame(st.session_state['comments'])
            
            # Ensure timestamp exists
            if 'timestamp' not in df_raw_comments.columns:
                df_raw_comments['timestamp'] = ''
            
            # Group by Lat/Lon to combine comments
            def create_timeline_html(group):
                html = "<div style='max-height: 200px; overflow-y: auto; color: black;'>" # color black for visibility
                html += "<b>Comments Timeline</b><hr style='margin: 4px 0;'/>"
                
                # Sort by timestamp (assuming formatted string YYYY-MM-DD...)
                group = group.sort_values('timestamp', ascending=False)
                
                for _, row in group.iterrows():
                    ts = row.get('timestamp', '')
                    txt = row.get('text', '')
                    time_display = f"<span style='font-size: 0.8em; color: #666;'>{ts}</span><br/>" if ts else ""
                    html += f"<div style='margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; font-size: 12px;'>{time_display}{txt}</div>"
                
                html += "</div>"
                return html

            # Grouping
            if not df_raw_comments.empty:
                df_comments_agg = df_raw_comments.groupby(['latitude', 'longitude']).apply(
                    lambda x: pd.Series({
                        'tooltip_html': create_timeline_html(x),
                        'count': len(x)
                    })
                ).reset_index()
            else:
                 df_comments_agg = pd.DataFrame(columns=['latitude', 'longitude', 'tooltip_html'])

            layer_comments = pdk.Layer(
                "ScatterplotLayer", 
                df_comments_agg,
                id="layer_comments",
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
    
        # st.pydeck_chart(r, key="main_map") # Old
        st.pydeck_chart(r, key="main_map", on_select="rerun", selection_mode="single-object")

        # Google Maps Links for Selected Points
        if not df_election.empty and len(df_election) < 20: 
            # Only show if reasonable number, otherwise list is too long. 
            # If search is active (implied by small number usually), show links.
            st.markdown("### 📍 Location Links")
            st.markdown("Click below to open in Google Maps:")
            
            # Use columns to make it compact? Or just a list. A list is clearer.
            for index, row in df_election.iterrows():
                lat = row['latitude']
                lon = row['longitude']
                name = row.get('ชื่อหน่วยเลือกตั้ง', 'Location')
                gmaps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                
                st.markdown(f"- **[{name}]({gmaps_url})**")
            st.markdown("---")
        
        # Legend (Only if Winner layer is active)
        if show_winner:
            st.markdown("""
            **Winning Percentage Intensity:**
            *   **> 45%**: High Intensity
            *   **30% - 45%**: Medium Intensity
            *   **< 30%**: Low Intensity
            """)
    
        # Comments / Annotation Section

        # --- Map Interaction Section (Always Visible) ---
        st.markdown("---")
        st.header("Map Interaction")
        st.caption("Select a point or district on the map to interact.")

        # --- Handle Map Selection ---
        default_lat = initial_view_state.latitude
        default_lon = initial_view_state.longitude
        default_text = ""
        
        # Check if selection exists in session state
        selection_state = st.session_state.get("main_map", {})
        if selection_state and "selection" in selection_state:
            selection = selection_state["selection"]
            if selection and "objects" in selection and selection["objects"]:
                # Get the last selected object
                obj = selection["objects"].values()
                # The format is {layer_id: [object_list]}
                for obj_list in obj:
                    if obj_list:
                        selected_data = obj_list[0]
                        # Try to extract coordinates
                        # Case 1: Point (Scatterplot) - usually has 'latitude', 'longitude' or 'position'
                        if 'latitude' in selected_data and 'longitude' in selected_data:
                            default_lat = selected_data['latitude']
                            default_lon = selected_data['longitude']
                            name_val = selected_data.get('ชื่อหน่วยเลือกตั้ง', '') or selected_data.get('name', 'Point')
                            default_text = f"Comment for: {name_val}"
                            
                        # Case 2: Polygon (GeoJson) - needs centroid calculation
                        elif 'geometry' in selected_data:
                            # Simple centroid approximation for display
                            # This depends on how Pydeck returns the geometry. 
                            # Usually it returns the GeoJSON geometry object.
                            geom = selected_data['geometry']
                            if geom['type'] == 'Polygon':
                                # Average of coordinates
                                coords = geom['coordinates'][0]
                                avg_lon = sum(p[0] for p in coords) / len(coords)
                                avg_lat = sum(p[1] for p in coords) / len(coords)
                                default_lat = avg_lat
                                default_lon = avg_lon
                                
                                sub_name = selected_data.get('sub_district_name', '') or selected_data.get('properties', {}).get('sub_district_name', 'District')
                                default_text = f"Comment for District: {sub_name}"
                            elif geom['type'] == 'MultiPolygon':
                                # Take first polygon for simplicity
                                coords = geom['coordinates'][0][0]
                                avg_lon = sum(p[0] for p in coords) / len(coords)
                                avg_lat = sum(p[1] for p in coords) / len(coords)
                                default_lat = avg_lat
                                default_lon = avg_lon
                                sub_name = selected_data.get('sub_district_name', '') or selected_data.get('properties', {}).get('sub_district_name', 'District')
                                default_text = f"Comment for District: {sub_name}"
                        
                        # Case 3: Position array [lon, lat] (common in some layers)
                        elif 'position' in selected_data:
                            default_lon = selected_data['position'][0]
                            default_lat = selected_data['position'][1]


        # --- UI: Tabs for Comment vs Color ---
        tab_comment, tab_color = st.tabs(["💬 Add Comment", "🎨 Color District"])
        
        with tab_comment:
            if show_comments:
                # Form to add comment
                with st.form("comment_form"):
                    c_col1, c_col2 = st.columns(2)
                    with c_col1:
                         c_lat = st.number_input("Latitude", value=default_lat, format="%.6f")
                    with c_col2:
                         c_lon = st.number_input("Longitude", value=default_lon, format="%.6f")
                
                    c_text = st.text_area("Comment Text", value=default_text)
                    c_submit = st.form_submit_button("Add Comment")
                
                    if c_submit:
                        if c_text:
                            import datetime
                            new_comment = {
                                "latitude": c_lat,
                                "longitude": c_lon,
                                "text": c_text,
                                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
            else:
                 st.info("Enable 'Comments' layer in sidebar to add comments.")
        
        with tab_color:
             # Check if we have a valid sub-district selected
             # We try to extract it from default_text or selected_data logic
             # Re-extract sub_name if possible for clarity
             valid_subdistrict = False
             current_sub_name = ""
             
             # Heuristic: Check if default_text startswith "Comment for District:"
             if default_text.startswith("Comment for District: "):
                 current_sub_name = default_text.replace("Comment for District: ", "").strip()
                 valid_subdistrict = True
             
             if valid_subdistrict:
                 st.markdown(f"**Target District:** `{current_sub_name}`")
                 
                 # Get current color
                 current_color = subdistrict_colors.get(current_sub_name, 'None')
                 
                 color_options = {
                     'None': 'Default (None)',
                     'orange': 'Orange (Som)',
                     'green': 'Low-Green',
                     'yellow': 'Low-Yellow',
                     'blue': 'Low-Blue'
                 }
                 
                 # Find index
                 options_keys = list(color_options.keys())
                 try:
                     default_ix = options_keys.index(current_color)
                 except:
                     default_ix = 0
                     
                 selected_color_key = st.selectbox(
                     "Assign Color", 
                     options=options_keys,
                     format_func=lambda x: color_options[x],
                     index=default_ix
                 )
                 
                 if st.button("Save Color Assignment"):
                     if selected_color_key == 'None':
                          pass
                     
                     save_subdistrict_color(current_sub_name, selected_color_key)
                     st.success(f"Assigned {selected_color_key} to {current_sub_name}")
                     time.sleep(1) 
                     st.rerun()
                     
             else:
                 st.info("Select a District polygon on the map to assign a color.")

        # --- Manage Comments at this Location ---
        if show_comments and st.session_state['comments']:
            # Import delete function
            from utils.data_utils import delete_comment
            
            # Filter comments for the currently selected location
            # Use small tolerance for float comparison or exact string match if they came from selection
            # Simple float equality usually works if values came from the same source
            current_loc_comments = [
                c for c in st.session_state['comments'] 
                if c['latitude'] == default_lat and c['longitude'] == default_lon
            ]
            
            if current_loc_comments:
                st.markdown("##### 🗑️ Manage Comments at this Location")
                
                for i, comment in enumerate(current_loc_comments):
                    col1, col2 = st.columns([0.8, 0.2])
                    with col1:
                        ts = comment.get('timestamp', '')
                        ts_str = f"**[{ts}]** " if ts else ""
                        st.markdown(f"{ts_str}{comment.get('text', '')}")
                    with col2:
                        # Unique key for each button
                        if st.button("❌", key=f"del_{i}_{comment.get('timestamp')}_{comment.get('text')[:5]}"):
                            # 1. Delete from backend
                            delete_comment(comment)
                            # 2. Delete from session state
                            if comment in st.session_state['comments']:
                                st.session_state['comments'].remove(comment)
                            st.rerun()
                st.divider()

        # Display Comments (Raw Table)
        if show_comments and st.session_state['comments']:
            st.markdown("---")
            st.subheader("Existing Comments")
            st.dataframe(pd.DataFrame(st.session_state['comments']))

    with tab_analysis:
        st.header("Analysis Details: Aggregated by Sub-district (ตำบล)")
        
        if not df_election.empty:
            df_display = calculate_votes_by_subdistrict(df_election)
            if not df_display.empty:
                st.dataframe(df_display, use_container_width=True)
                
                # Show some metrics
                total_voters = df_display['ผู้มีสิทธิ์'].sum() if 'ผู้มีสิทธิ์' in df_display.columns else 0
                total_turnout = df_display['ผู้มาใช้สิทธิ์'].sum() if 'ผู้มาใช้สิทธิ์' in df_display.columns else 0
                
                # Display generic metrics if columns match expectations
                if total_voters > 0:
                    st.metric("Total Eligible Voters", f"{total_voters:,}")
                    st.metric("Total Turnout", f"{total_turnout:,}")
            else:
                 st.info("Aggregation returned empty results (check 'ตำบล' column).")
        else:
            st.info("No election data loaded.")

if __name__ == "__main__":
    main()
