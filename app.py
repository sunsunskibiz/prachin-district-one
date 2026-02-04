import streamlit as st
import pandas as pd
import pydeck as pdk
import time
import logging
import sys
import os
import yaml
import datetime # Added for Visit Record
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth

# Import from new utils
from utils.constants import CSV_FILE, KML_FILE, GCS_BUCKET_NAME
from utils.geo_utils import create_mask_polygon, extract_subdistrict_name, extract_amphoe_name, process_path_overlaps
from utils.data_utils import load_comments, save_comment, load_csv_data, load_kml_data, calculate_votes_by_subdistrict, load_campaign_pins, load_subdistrict_colors, save_subdistrict_color, load_visit_records, save_visit_record
from utils.gcs_utils import list_gcs_kml_files, upload_to_gcs, load_kml_from_gcs, get_gcs_client
from utils.html_utils import get_subdistrict_tooltip, get_election_html, aggregate_tooltips, create_timeline_html, get_visit_tooltip

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

def create_map_layers(
    gdf_districts, subdistrict_colors,
    show_districts, show_winner, show_points, show_campaign_pins, show_comments,
    show_color_orange, show_color_green, show_color_brown, show_color_blue,
    show_visit_heatmap, visit_records, # New Arguments
    active_uploaded_layers, kml_layers,
    df_map_points, gdf_campaign_pins, df_comments_agg
):
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

        # 2. Polygon Layer - Blue Lines Style
        def get_district_fill_color(row):
             s_name = row.get('sub_district_name', '')
             assigned_color = subdistrict_colors.get(s_name, None)
             
             base_alpha = 140
             
             if assigned_color == 'orange' and show_color_orange:
                 return [255, 165, 0, base_alpha]
             elif assigned_color == 'green' and show_color_green:
                 return [144, 238, 144, base_alpha]
             elif assigned_color == 'brown' and show_color_brown:
                 return [210, 180, 140, base_alpha]
             elif assigned_color == 'blue' and show_color_blue:
                 return [173, 216, 230, base_alpha]
             
             # Visit Heatmap Override
             if show_visit_heatmap:
                 visits = visit_records.get(s_name, [])
                 count = len(visits)
                 if count > 0:
                     if count < 3: return [255, 204, 128, 200]    # Level 1: Light Orange
                     elif count < 7: return [255, 165, 0, 200]    # Level 2: Medium Orange
                     else: return [230, 81, 0, 200]               # Level 3: Dark Orange (Reddish)

             return [0, 0, 0, 0] 

        gdf_districts['const_fill_color'] = gdf_districts.apply(get_district_fill_color, axis=1)

        layer_districts = pdk.Layer(
            "GeoJsonLayer",
            gdf_districts,
            id="layer_districts",
            opacity=1.0,
            stroked=True,
            filled=True, 
            get_fill_color="const_fill_color", 
            get_line_color=[0, 0, 255, 255],
            get_line_width=30,
            lineWidthMinPixels=2, 
            pickable=True, 
            auto_highlight=True,
            wireframe=True,
            highlight_color=[0, 0, 255, 128],
        )
        layers.append(layer_districts)

    if active_uploaded_layers:
        layers_to_process = []
        for name in active_uploaded_layers:
            layer = kml_layers.get(name)
            if layer is not None:
                layers_to_process.append(layer)

        if layers_to_process:
             # Using the process_path_overlaps (assuming st.spinner context is handled by caller or ignored here)
             # To avoid UI blocking logic inside helper, we just run it. 
             # Note: 'process_path_overlaps' is cached so it should be fast.
             gdf_merged = process_path_overlaps(layers_to_process, active_uploaded_layers)
        
             if gdf_merged is not None and not gdf_merged.empty:
                layer_uploaded = pdk.Layer(
                    "GeoJsonLayer",
                    gdf_merged,
                    id="layer-uploaded-merged",
                    opacity=1.0,
                    stroked=True,
                    filled=False, 
                    get_line_color="color",
                    get_line_width=30,
                    lineWidthMinPixels=2,
                    pickable=False,
                )
                layers.append(layer_uploaded)

    if show_winner and gdf_districts is not None and 'Winner' in gdf_districts.columns:
        def get_winner_color(row):
            winner = row.get('Winner', '')
            pct = row.get('Winner_Pct', 0)
            try:
                pct_val = float(pct)
            except (ValueError, TypeError):
                pct_val = 0

            if pct_val > 45: alpha = 200
            elif pct_val >= 30: alpha = 120
            else: alpha = 60

            if winner == 'ภูมิใจไทย': return [0, 0, 255, alpha] 
            elif winner == 'ก้าวไกล': return [255, 165, 0, alpha]
            elif winner == 'เพื่อไทย': return [255, 0, 0, alpha]
            else: return [200, 200, 200, 50]
        
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

    if show_points and df_map_points is not None and not df_map_points.empty:
        layer_points = pdk.Layer(
            "ScatterplotLayer",
            df_map_points,
            id="layer_points",
            get_position=['longitude', 'latitude'],
            get_color="point_color" if "point_color" in df_map_points.columns else [255, 65, 54, 200],
            get_radius=100,
            pickable=True,
            auto_highlight=True,
        )
        layers.append(layer_points)
        
    if show_campaign_pins and gdf_campaign_pins is not None:
         import math
         layer_campaign = pdk.Layer(
            "ColumnLayer",
            gdf_campaign_pins,
            id="layer_campaign_pins",
            get_position=['geometry.coordinates[0]', 'geometry.coordinates[1]'],
            get_fill_color=[128, 0, 128, 200],
            get_line_color=[255, 255, 255, 255],
            get_line_width=2,
            radius=100,
            disk_resolution=4,
            get_angle=math.pi / 4,
            get_elevation=0,
            extruded=False,
            stroked=True,
            pickable=True,
            auto_highlight=True,
        )
         layers.append(layer_campaign)
    
    if show_comments and df_comments_agg is not None and not df_comments_agg.empty:
        layer_comments = pdk.Layer(
            "ScatterplotLayer", 
            df_comments_agg,
            id="layer_comments",
            get_position=['longitude', 'latitude'],
            get_fill_color=[0, 255, 0, 255],
            get_radius=300, 
            pickable=True,
            auto_highlight=True,
        )
        layers.append(layer_comments)

    return layers

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
        
        # Load Visit Records
        visit_records = load_visit_records()

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
    
    # --- Sidebar Controls (Moved here to be available for all tabs) ---
    st.sidebar.header("Layer Controls")
    show_districts = st.sidebar.checkbox("แสดงเขตตำบล", value=True)
    show_winner = st.sidebar.checkbox("แสดงเขตผู้ชนะ", value=False)
    show_points = st.sidebar.checkbox("หน่วยเลือกตั้ง", value=True)
    show_campaign_pins = st.sidebar.checkbox("จุดติดป้าย", value=False)

    st.sidebar.markdown("**Comment Layers:**")
    show_comments = st.sidebar.checkbox("General Comments", value=True)
    show_point_comments = st.sidebar.checkbox("Point Contact Info", value=True)

    st.sidebar.markdown("**Color Highlights:**")
    show_color_orange = st.sidebar.checkbox("เทสีส้ม", value=False)
    show_color_green = st.sidebar.checkbox("เทสีเขียว", value=False)
    show_color_brown = st.sidebar.checkbox("เทสีน้ำตาล", value=False)
    show_color_blue = st.sidebar.checkbox("เทสีฟ้า", value=False)
    
    st.sidebar.markdown("**Visit Analysis:**")
    show_visit_heatmap = st.sidebar.checkbox("Show Visit Heatmap", value=False)
    if show_visit_heatmap:
        st.sidebar.caption("🟠 Level 1 (<3): Light")
        st.sidebar.caption("🟠 Level 2 (3-6): Medium")
        st.sidebar.caption("🔴 Level 3 (7+): Dark")
    
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
                how='inner'
            )
            # Fill NaN Winner with "Unknown" and 0 for logic processing but keep NaNs for display where appropriate
            if 'Winner' in gdf_districts.columns:
                 gdf_districts['Winner'] = gdf_districts['Winner'].fillna("Unknown")
            if 'Winner_Pct' in gdf_districts.columns:
                 gdf_districts['Winner_Pct'] = gdf_districts['Winner_Pct'].fillna(0)
                 
        # Generate Tooltips for Districts (Needed for all maps)
        gdf_districts['tooltip_html'] = gdf_districts.apply(get_subdistrict_tooltip, axis=1)

    # Pre-process Data for Points (Moved out of tabs for access)
    df_map_points = pd.DataFrame()
    filtered_locations = None
    selected_units = []
    
    # 1. Search Logic (Pre-calc)
    if not df_election.empty and 'ชื่อหน่วยเลือกตั้ง' in df_election.columns:
         # We need to know if searching is active to filter locations, 
         # BUT the UI for search is inside Overview tab. 
         # To make 'df_map_points' available everywhere, we might need to render search UI early OR just default to all points here 
         # and apply filtering later? 
         # Actually, the user wants the map in Settings to work. 
         # Let's initialize defaults here and refine inside Overview if needed? 
         # No, 'df_map_points' depends on 'filtered_locations' which depends on 'selected_units'.
         # Let's keep search UI in Overview but maybe move the aggregation logic to a shared block.
         pass # Logic stays in overview for UI, but aggregation function is reused.
         
    # 2. Aggregation Logic
    if not df_election.empty:
         df_election['tooltip_html'] = df_election.apply(get_election_html, axis=1)
         df_map_points = df_election.groupby(['latitude', 'longitude'])['tooltip_html'].agg(aggregate_tooltips).reset_index()

    # 3. Comments Logic
    df_comments_agg = pd.DataFrame()
    if 'comments' not in st.session_state:
        st.session_state['comments'] = load_comments()
        
    if st.session_state['comments']:
        df_raw = pd.DataFrame(st.session_state['comments'])
        if 'timestamp' not in df_raw.columns: df_raw['timestamp'] = ''
        if not df_raw.empty:
             df_comments_agg = df_raw.groupby(['latitude', 'longitude']).apply(
                lambda x: pd.Series({
                    'tooltip_html': create_timeline_html(x),
                    'count': len(x)
                })
             ).reset_index()
    
    # --- Main Navigation (Radio as Tabs for State Persistence) ---
    if 'active_tab' not in st.session_state:
        st.session_state['active_tab'] = "Overview"

    st.session_state['active_tab'] = st.radio(
        "Navigation", 
        options=["Overview", "Analysis Details", "Color Assign", "Comment Assign", "Point Comment", "Visit Record"], 
        horizontal=True,
        label_visibility="collapsed",
        key="nav_radio",
        index=["Overview", "Analysis Details", "Color Assign", "Comment Assign", "Point Comment", "Visit Record"].index(st.session_state['active_tab'])
    )

    # Note: We use st.session_state['active_tab'] to control visibility
    # This ensures only the active component runs, improving performance and state stability.

    # --- TAB: LAYER SETTINGS (Color Assign) ---
    if st.session_state['active_tab'] == "Color Assign":
        st.header("Color Management")
        
        col_map, col_form = st.columns([2, 1])
        
        with col_map:
            st.subheader("Assign Color to District")
            
            # Helper map for selection
            st.markdown("Select a district on the map to assign color:")
            
            # Build Layers for Settings Map
            # Note: We use the *current* visibility settings from this tab + sidebar defaults
            layers_settings = create_map_layers(
                gdf_districts, subdistrict_colors,
                show_districts, show_winner, False, False, False, # Hide points/comments in settings map for clarity
                show_color_orange, show_color_green, show_color_brown, show_color_blue,
                False, {}, # No Heatmap in Settings Map
                [], st.session_state['kml_layers'], 
                None, None, None 
            )
            
            # View State for Settings Map (can be static or same as main)
            view_state_settings = pdk.ViewState(latitude=14.0, longitude=101.5, zoom=9)
            
            st.pydeck_chart(
                pdk.Deck(
                    layers=layers_settings,
                    initial_view_state=view_state_settings,
                    map_style="mapbox://styles/mapbox/light-v9",
                    tooltip={"html": "{tooltip_html}", "style": {"color": "white"}}
                ),
                key="settings_map",
                on_select="rerun",
                selection_mode="single-object",
                height=600
            )

            # --- Color Coverage Metrics ---
            st.divider()
            st.subheader("Color Coverage (Total: 26 Districts)")
            
            # Count colors
            counts = {
                'orange': 0,
                'green': 0,
                'brown': 0,
                'blue': 0
            }
            
            for color in subdistrict_colors.values():
                if color in counts:
                    counts[color] += 1
            
            # Calculate Percentages (Fixed denominator of 26)
            total_districts = 26
            
            m1, m2, m3, m4 = st.columns(4)
            
            with m1:
                pct = (counts['orange'] / total_districts) * 100
                st.metric("สีส้ม (Orange)", f"{counts['orange']} ({pct:.1f}%)")
                
            with m2:
                pct = (counts['green'] / total_districts) * 100
                st.metric("สีเขียว (Green)", f"{counts['green']} ({pct:.1f}%)")
                
            with m3:
                pct = (counts['brown'] / total_districts) * 100
                st.metric("สีน้ำตาล (Brown)", f"{counts['brown']} ({pct:.1f}%)")
                
            with m4:
                pct = (counts['blue'] / total_districts) * 100
                st.metric("สีฟ้า (Blue)", f"{counts['blue']} ({pct:.1f}%)")

        with col_form:
            # Check if selection exists in session state (settings_map)
            selection_state = st.session_state.get("settings_map", {})
            
            # Check main map selection as fallback if user just switched tabs (optional, but good UX)
            if not selection_state.get("selection"):
                 selection_state = st.session_state.get("main_map", {})
            
            # Logic to determine selected district
            default_sub_name = ""
            valid_subdistrict = False
            
            if selection_state and "selection" in selection_state:
                selection = selection_state["selection"]
                if selection and "objects" in selection and selection["objects"]:
                    # Get the last selected object
                    obj = selection["objects"].values()
                    for obj_list in obj:
                        if obj_list:
                            selected_data = obj_list[0]
                            # Try to extract sub_district_name
                            if 'sub_district_name' in selected_data:
                                default_sub_name = selected_data['sub_district_name']
                                valid_subdistrict = True
                            elif 'properties' in selected_data and 'sub_district_name' in selected_data['properties']:
                                default_sub_name = selected_data['properties']['sub_district_name']
                                valid_subdistrict = True
            
            if valid_subdistrict:
                 st.markdown(f"**Target District:** `{default_sub_name}`")
                 
                 # Get current color
                 current_color = subdistrict_colors.get(default_sub_name, 'None')
                 
                 color_options = {
                     'None': 'Default (None)',
                     'orange': 'สีส้ม',
                     'green': 'สีเขียว',
                     'brown': 'สีน้ำตาล',
                     'blue': 'สีฟ้า'
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
                     
                     save_subdistrict_color(default_sub_name, selected_color_key)
                     st.success(f"Assigned {selected_color_key} to {default_sub_name}")
                     time.sleep(1) 
                     st.rerun()
                     
            else:
                 st.info("Select a District polygon on the map to assign a color.")

    # --- TAB: COMMENT ASSIGN ---
    if st.session_state['active_tab'] == "Comment Assign":
        st.header("Comment Assignment")
        st.caption("Select a district or point on the map to add a comment.")
        
        col_map, col_form = st.columns([2, 1])
        
        with col_map:
            # Layers for Comment Map (Districts + Comments)
            layers_comment = create_map_layers(
                gdf_districts, subdistrict_colors,
                True, # show_districts
                False, # show_winner
                False, # show_points
                False, # show_campaign_pins
                True,  # show_comments (Always show in this tab?) Let's respect sidebar or force true?
                       # User might want to toggle. Let's respect sidebar 'show_comments'.
                show_color_orange, show_color_green, show_color_brown, show_color_blue,
                False, {},
                [], {}, 
                None, None, df_comments_agg
            )
            
            view_state_comment = pdk.ViewState(latitude=14.0, longitude=101.5, zoom=9)
            
            st.pydeck_chart(
                pdk.Deck(
                    layers=layers_comment,
                    initial_view_state=view_state_comment,
                    map_style="mapbox://styles/mapbox/light-v9",
                    tooltip={"html": "{tooltip_html}", "style": {"color": "white"}}
                ),
                key="comment_map",
                on_select="rerun",
                selection_mode="single-object",
                height=600
            )

        with col_form:
            # --- Handle Map Selection for Comment Tab ---
            default_lat_c = 14.0
            default_lon_c = 101.5
            default_text_c = ""
            
            selection_state_c = st.session_state.get("comment_map", {})
            if selection_state_c and "selection" in selection_state_c:
                selection = selection_state_c["selection"]
                if selection and "objects" in selection and selection["objects"]:
                    obj = selection["objects"].values()
                    for obj_list in obj:
                        if obj_list:
                            selected_data = obj_list[0]
                            # Case 1: Point
                            if 'latitude' in selected_data and 'longitude' in selected_data:
                                default_lat_c = selected_data['latitude']
                                default_lon_c = selected_data['longitude']
                                name_val = selected_data.get('ชื่อหน่วยเลือกตั้ง', '') or selected_data.get('name', 'Point')
                                default_text_c = f"Comment for: {name_val}"
                            # Case 2: Geometry (Polygon)
                            elif 'geometry' in selected_data:
                                geom = selected_data['geometry']
                                if geom['type'] == 'Polygon':
                                    coords = geom['coordinates'][0]
                                    avg_lon_c = sum(p[0] for p in coords) / len(coords)
                                    avg_lat_c = sum(p[1] for p in coords) / len(coords)
                                    default_lat_c = avg_lat_c
                                    default_lon_c = avg_lon_c
                                    sub_name = selected_data.get('sub_district_name', '') or selected_data.get('properties', {}).get('sub_district_name', 'District')
                                    default_text_c = f"Comment for District: {sub_name}"
                                elif geom['type'] == 'MultiPolygon':
                                    coords = geom['coordinates'][0][0]
                                    avg_lon_c = sum(p[0] for p in coords) / len(coords)
                                    avg_lat_c = sum(p[1] for p in coords) / len(coords)
                                    default_lat_c = avg_lat_c
                                    default_lon_c = avg_lon_c
                                    sub_name = selected_data.get('sub_district_name', '') or selected_data.get('properties', {}).get('sub_district_name', 'District')
                                    default_text_c = f"Comment for District: {sub_name}"

            st.subheader("Add Comment")
            with st.form("comment_form_tab"):
                c_lat = st.number_input("Latitude", value=default_lat_c, format="%.6f")
                c_lon = st.number_input("Longitude", value=default_lon_c, format="%.6f")
                c_text = st.text_area("Comment Value", value=default_text_c)
                c_submit = st.form_submit_button("Save Comment")
                
                if c_submit:
                    if c_text:

                        new_comment = {
                            "latitude": c_lat,
                            "longitude": c_lon,
                            "text": c_text,
                            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "ชื่อหน่วยเลือกตั้ง": "Comment: " + c_text[:20]
                        }
                        st.session_state['comments'].append(new_comment)
                        save_comment(new_comment)
                        st.success("Saved!")
                        st.rerun()
                    else:
                        st.warning("Enter text.")

            # Manage Comments at Location
            # Filter comments for the currently selected location (approx match)
            current_loc_comments = [
                c for c in st.session_state.get('comments', [])
                if abs(c['latitude'] - default_lat_c) < 0.0001 and abs(c['longitude'] - default_lon_c) < 0.0001
            ]
            
            if current_loc_comments:
                st.divider()
                st.markdown("**Manage Comments Here:**")
                from utils.data_utils import delete_comment
                for i, comment in enumerate(current_loc_comments):
                    col_txt, col_del = st.columns([0.8, 0.2])
                    with col_txt:
                        st.caption(f"{comment.get('timestamp','')}: {comment.get('text','')}")
                    with col_del:
                        if st.button("Del", key=f"del_tab_{i}_{comment.get('timestamp')}"):
                            delete_comment(comment)
                            if comment in st.session_state['comments']:
                                st.session_state['comments'].remove(comment)
                            st.rerun()

    # --- TAB: POINT COMMENT (Election Points) ---
    if st.session_state['active_tab'] == "Point Comment":
        st.header("Point Comment (Election Units)")
        st.caption("Select an Election Point (Red Dot) to add a contact comment.")
        
        col_map_p, col_form_p = st.columns([2, 1])
        
        with col_map_p:
            # Prepare DataFrame with custom tooltips for this tab
            df_points_display = df_map_points.copy()
            
            # Convert session comments to DF
            current_comments = pd.DataFrame(st.session_state.get('comments', []))
            
            # Update tooltip column AND Color
            from utils.html_utils import get_point_comment_tooltip
            if not df_points_display.empty:
                 # Helper to check if unit has comment
                 units_with_comments = set()
                 if not current_comments.empty and 'target_unit' in current_comments.columns:
                     units_with_comments = set(current_comments['target_unit'].unique())
                 
                 def set_props(row):
                     # Tooltip
                     tt = get_point_comment_tooltip(row, current_comments, df_election)
                     # Color
                     # We need to check if ANY unit at this location has a comment
                     lat = row['latitude']
                     lon = row['longitude']
                     
                     color = [255, 65, 54, 200] # Default Red
                     
                     if not df_election.empty:
                        matches = df_election[
                            (df_election['latitude'] == lat) & 
                            (df_election['longitude'] == lon)
                        ]
                        if not matches.empty:
                            units_at_loc = matches['ชื่อหน่วยเลือกตั้ง'].unique().tolist()
                            # If any unit at this location is in units_with_comments
                            if any(u in units_with_comments for u in units_at_loc):
                                color = [0, 255, 0, 200] # Green
                     
                     return pd.Series([tt, color], index=['tooltip_html', 'point_color'])

                 df_points_display[['tooltip_html', 'point_color']] = df_points_display.apply(set_props, axis=1)

            # Show ONLY Points (and districts for context, but no winner colors)
            layers_point = create_map_layers(
                gdf_districts, subdistrict_colors,
                True, # show_districts
                False, # show_winner
                True, # show_points (Critical!)
                False, # show_campaign_pins
                False, # show_comments (Hide generic comments to focus on points?)
                False, False, False, False, # No colors
                False, {}, # show_visit_heatmap, visit_records
                [], {}, 
                df_points_display, # Pass map points with updated tooltips
                None, None # No point comments aggregation here yet or pass generic if needed
            )
            
            view_state_point = pdk.ViewState(latitude=14.0, longitude=101.5, zoom=10)
            
            st.pydeck_chart(
                pdk.Deck(
                    layers=layers_point,
                    initial_view_state=view_state_point,
                    map_style="mapbox://styles/mapbox/light-v9",
                    tooltip={"html": "{tooltip_html}", "style": {"color": "white"}}
                ),
                key="point_comment_map",
                on_select="rerun",
                selection_mode="single-object",
                height=600
            )

            # --- Metrics ---
            if not df_points_display.empty and 'point_color' in df_points_display.columns:
                 # Count Green
                 # Note: point_color is a list/array
                 def is_green(c):
                     return c[0] == 0 and c[1] == 255
                 
                 green_count = df_points_display['point_color'].apply(is_green).sum()
                 total_points = len(df_points_display)
                 pct = (green_count / total_points) * 100 if total_points > 0 else 0
                 
                 st.metric("Contact Info Coverage", f"{green_count} / {total_points}", f"{pct:.1f}%")
        
        with col_form_p:
            # Handle Selection
            default_p_name = ""
            valid_point = False
            
            selection_state_p = st.session_state.get("point_comment_map", {})
            if selection_state_p and "selection" in selection_state_p:
                selection = selection_state_p["selection"]
                if selection and "objects" in selection and selection["objects"]:
                    obj = selection["objects"].values()
                    for obj_list in obj:
                        if obj_list:
                            selected_data = obj_list[0]
                            # Look for point data
                            if 'ชื่อหน่วยเลือกตั้ง' in selected_data:
                                default_p_name = selected_data['ชื่อหน่วยเลือกตั้ง']
                                valid_point = True
            
            if valid_point:
                st.subheader(f"Unit: {default_p_name}")
                
                with st.form("point_contact_form"):
                    c_name = st.text_input("Contact Name")
                    c_tel = st.text_input("Tel")
                    c_line = st.text_input("Line ID")
                    c_note = st.text_area("Note/Comment")
                    
                    submitted = st.form_submit_button("Save Contact Info")
                    
                    if submitted:
                        if c_name or c_note:
                            new_contact = {
                                "target_unit": default_p_name,
                                "contact_name": c_name,
                                "contact_tel": c_tel,
                                "contact_line": c_line,
                                "text": c_note, # Compatible with generic comment schema
                                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "latitude": 0, # Placeholder or lookup if needed
                                "longitude": 0 # Placeholder
                            }
                            # Optional: Lookup lat/lon from df_map_points for completeness
                            if not df_map_points.empty:
                                match = df_map_points[df_map_points['tooltip_html'].str.contains(default_p_name, regex=False)]
                                # This is weak. Better lookup from df_election raw or just ignore lat/lon for point comments?
                                # Let's ignore for now, this is relational data.
                            
                            st.session_state['comments'].append(new_contact)
                            save_comment(new_contact)
                            st.success(f"Saved for {default_p_name}")
                            st.rerun()
                            
                # List existing for this unit
                current_comments = st.session_state.get('comments', [])
                unit_comments = [c for c in current_comments if c.get('target_unit') == default_p_name]
                
                if unit_comments:
                    st.divider()
                    st.write("Existing Contacts:")
                    from utils.data_utils import delete_comment
                    for i, u_comm in enumerate(unit_comments):
                         with st.container():
                             st.caption(f"**{u_comm.get('contact_name')}** ({u_comm.get('timestamp')})")
                             st.write(u_comm.get('text'))
                             if st.button("Delete", key=f"del_p_{i}_{default_p_name}"):
                                 delete_comment(u_comm)
                                 if u_comm in st.session_state['comments']:
                                     st.session_state['comments'].remove(u_comm)
                                 st.rerun()
                                 
            else:
                 st.info("Select a Red Point (Election Unit) to add contact info.")

    # --- TAB: VISIT RECORD ---
    if st.session_state['active_tab'] == "Visit Record":
        st.header("Visit Record Management")
        
        col_map_v, col_form_v = st.columns([2, 1])
        
        with col_map_v:
            st.subheader("Select District to Add Visit")
            
            # Prepare special GDF for Visit Display (Custom Tooltip)
            gdf_visit_display = gdf_districts.copy() if gdf_districts is not None else None
            if gdf_visit_display is not None:
                # Merge visit records for tooltip display
                gdf_visit_display['visit_records'] = gdf_visit_display['sub_district_name'].map(visit_records)
                # Apply Visit-specific Tooltip
                gdf_visit_display['tooltip_html'] = gdf_visit_display.apply(get_visit_tooltip, axis=1)

            # Map Layers (Districts + Heatmap if toggle is ON by sidebar, NO points)
            # We want to show the heatmap here implicitly if useful?
            # Or just standard districts. Let's use the standard district view.
            # If sidebar 'Show Visit Heatmap' is checked, layers will already have color overrides.
            
            layers_visit = create_map_layers(
                gdf_visit_display, subdistrict_colors,
                True, # show_districts
                False, # show_winner
                False, # show_points
                False, # show_campaign_pins
                False, # show_comments
                show_color_orange, show_color_green, show_color_brown, show_color_blue,
                show_visit_heatmap, visit_records, # Pass visit data for coloring
                active_uploaded_layers, st.session_state['kml_layers'], 
                None, None, None 
            )
            
            view_state_visit = pdk.ViewState(latitude=14.0, longitude=101.5, zoom=9)
            
            st.pydeck_chart(
                pdk.Deck(
                    layers=layers_visit,
                    initial_view_state=view_state_visit,
                    map_style="mapbox://styles/mapbox/light-v9",
                    tooltip={"html": "{tooltip_html}", "style": {"color": "white"}}
                ),
                key="visit_map",
                on_select="rerun",
                selection_mode="single-object",
                height=600
            )

        with col_form_v:
            # Handle Selection
            default_sub_name_v = ""
            valid_subdistrict_v = False
            
            selection_state_v = st.session_state.get("visit_map", {})
            
            # Check selection
            if selection_state_v and "selection" in selection_state_v:
                selection = selection_state_v["selection"]
                if selection and "objects" in selection and selection["objects"]:
                    obj = selection["objects"].values()
                    for obj_list in obj:
                        if obj_list:
                            selected_data = obj_list[0]
                            # Try to extract sub_district_name
                            if 'sub_district_name' in selected_data:
                                default_sub_name_v = selected_data['sub_district_name']
                                valid_subdistrict_v = True
                            elif 'properties' in selected_data and 'sub_district_name' in selected_data['properties']:
                                default_sub_name_v = selected_data['properties']['sub_district_name']
                                valid_subdistrict_v = True
            
            if valid_subdistrict_v:
                 st.markdown(f"### District: `{default_sub_name_v}`")
                 
                 # Show existing visits
                 existing_visits = visit_records.get(default_sub_name_v, [])
                 
                 st.markdown("**Existing Visits:**")
                 if existing_visits:
                     for v_date in existing_visits:
                         st.text(f"• {v_date}")
                 else:
                     st.caption("No visits recorded yet.")
                     
                 st.divider()
                 
                 # Add New Visit
                 with st.form("add_visit_form"):
                     new_date = st.date_input("Select Date", value=datetime.datetime.now())
                     add_btn = st.form_submit_button("Add Visit Record")
                     
                     if add_btn:
                         date_str = new_date.strftime("%Y-%m-%d")
                         save_visit_record(default_sub_name_v, date_str)
                         
                         # Update local state immediately for UI response
                         if default_sub_name_v not in visit_records:
                             visit_records[default_sub_name_v] = []
                         if date_str not in visit_records[default_sub_name_v]:
                             visit_records[default_sub_name_v].append(date_str)
                             
                         st.success(f"Added visit on {date_str}")
                         time.sleep(1)
                         st.rerun()
                         
            else:
                 st.info("Select a District on the map to manage visit records.")

            

    # --- TAB: OVERVIEW ---
    if st.session_state['active_tab'] == "Overview":
        selected_units = []
        filtered_locations = None
        
        # Search Feature (Main Area)
        if not df_election.empty and 'ชื่อหน่วยเลือกตั้ง' in df_election.columns:
            all_units = sorted(df_election['ชื่อหน่วยเลือกตั้ง'].astype(str).unique().tolist())
            selected_units = st.multiselect("🔍 Search Election Unit", options=all_units, placeholder="Type to search unit name...")
            
            if selected_units:
                # Find locations of selected units
                # We do NOT filter df_election here so that aggregation picks up neighbors
                target_rows = df_election[df_election['ชื่อหน่วยเลือกตั้ง'].isin(selected_units)]
                filtered_locations = target_rows[['latitude', 'longitude']].drop_duplicates()
                
                st.success(f"Found {len(target_rows)} matching units. Showing all units at these locations.")
                show_points = True # Force show points on map if user is searching

        if gdf_districts is not None and not gdf_districts.empty:
            # Helper to safely get KML columns - for default districts
            kml_cols = gdf_districts.columns
            # Tooltips are now pre-calculated
        else:
            st.sidebar.warning("Failed to load default KML polygons")

        if st.session_state['kml_layers']:
             total_features = sum(len(gdf) for gdf in st.session_state['kml_layers'].values())
             st.sidebar.success(f"Loaded {len(st.session_state['kml_layers'])} files ({total_features} features)")

        if not df_election.empty:
             # Prepare Election Tooltip HTML
             # get_election_html is now imported from utils.html_utils
             df_election['tooltip_html'] = df_election.apply(get_election_html, axis=1)

             # --- GRID LAYOUT AGGREGATION FOR OVERLAPPING POINTS ---
             # Group by Lat/Lon and aggregate tooltips into a Grid (3 per row)
             # aggregate_tooltips is now imported from utils.html_utils

             
             # Create new display dataframe with unique coordinates (Now handled before tabs)
             # df_map_points = df_election.groupby(['latitude', 'longitude'])['tooltip_html'].agg(aggregate_tooltips).reset_index()
             
             # Apply Search Filter to Map Points
             if filtered_locations is not None:
                 df_map_points = df_map_points.merge(filtered_locations, on=['latitude', 'longitude'], how='inner')

    
        # Initialize Session State for Comments from File (Now handled before tabs)
        # if 'comments' not in st.session_state:
        #    st.session_state['comments'] = load_comments()

        # Sidebar Controls
    
        # Prepare Pydeck Layers (Using Helper)
        
        # Apply Search Filter to Map Points for Main Map
        df_map_points_filtered = df_map_points.copy() if not df_map_points.empty else pd.DataFrame()
        
        if filtered_locations is not None and not df_map_points_filtered.empty:
             df_map_points_filtered = df_map_points_filtered.merge(
                filtered_locations, on=['latitude', 'longitude'], how='inner'
             )

        # Filter Comments based on Sidebar
        df_comments_final = pd.DataFrame()
        if df_comments_agg is not None and not df_comments_agg.empty:
            # We need to filter the SOURCE comments first then re-aggregate? 
            # Or filter the aggregated ones? DF_comments_agg is aggregated by location.
            # But we don't have 'target_unit' in agg? 
            # We need to re-aggregate if we filter! 
            # Re-doing aggregation here is safer.
            
            raw_comments = pd.DataFrame(st.session_state.get('comments', []))
            if not raw_comments.empty:
                # 1. Identify types
                # Point Contacts have 'target_unit'. General ones might not?
                if 'target_unit' not in raw_comments.columns:
                    raw_comments['target_unit'] = None
                
                # Filter
                mask_general = raw_comments['target_unit'].isna() | (raw_comments['target_unit'] == '')
                mask_point = ~mask_general
                
                parts = []
                if show_comments:
                    parts.append(raw_comments[mask_general])
                if show_point_comments:
                    parts.append(raw_comments[mask_point])
                
                if parts:
                    df_filtered_source = pd.concat(parts)
                    if not df_filtered_source.empty:
                        # Re-aggregate
                        # from utils.html_utils import create_timeline_html (Removed to avoid shadowing)
                        df_comments_final = df_filtered_source.groupby(['latitude', 'longitude']).apply(
                            lambda x: pd.Series({
                                'tooltip_html': create_timeline_html(x),
                                'count': len(x)
                            })
                        ).reset_index()

        layers = create_map_layers(
            gdf_districts, subdistrict_colors,
            show_districts, show_winner, show_points, show_campaign_pins, 
            True, # Always True for comments layer, as we control it via df_comments_final being empty or not
            show_color_orange, show_color_green, show_color_brown, show_color_blue,
            show_visit_heatmap, visit_records,
            active_uploaded_layers, st.session_state['kml_layers'],
            df_map_points_filtered, gdf_campaign_pins, df_comments_final
        )
        
        # Map State
        # Center map on data
        if not df_election.empty:
            # Dynamic Zoom Logic
            # If we match a search (filtered_locations), focus on that. 
            # Otherwise focus on full dataset.
            
            target_df = df_election
            if filtered_locations is not None and not filtered_locations.empty:
                target_df = filtered_locations
                
            row_count = len(target_df)
            
            # Default zoom
            zoom_level = 10
            
            if row_count == 1:
                zoom_level = 15
            elif row_count < 5:
                zoom_level = 13
            
            initial_view_state = pdk.ViewState(
                latitude=target_df['latitude'].mean(),
                longitude=target_df['longitude'].mean(),
                zoom=zoom_level,
                pitch=0,
            )
        else:
            initial_view_state = pdk.ViewState( latitude=14.0, longitude=101.5, zoom=10 ) 

        # Tooltip
        # We use the pre-calculated 'tooltip_html' column from dataframes
        tooltip = {
            "html": "{tooltip_html}", 
            "style": {"backgroundColor": "steelblue", "color": "white", "maxWidth": "1000px"} # Large width for 3-col grid
        }
    
        # Render Map - Using Selected Style
        r = pdk.Deck(
            layers=layers,
            initial_view_state=initial_view_state,
            map_style=selected_map_style, 
            tooltip=tooltip
        )
    
        # st.pydeck_chart(r, key="main_map") # Old
        # st.pydeck_chart(r, key="main_map") # Old
        st.pydeck_chart(r, key="main_map", height=700)

        # Google Maps Links for Selected Points
        # Use filtered list if search is active, otherwise use full list (limited to 20)
        df_links = df_election
        if selected_units:
            df_links = df_election[df_election['ชื่อหน่วยเลือกตั้ง'].isin(selected_units)]

        if not df_links.empty and len(df_links) < 20: 
            # Only show if reasonable number, otherwise list is too long. 
            # If search is active (implied by small number usually), show links.
            st.markdown("### 📍 Location Links")
            st.markdown("Click below to open in Google Maps:")
            
            # Use columns to make it compact? Or just a list. A list is clearer.
            for index, row in df_links.iterrows():
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





    # --- TAB: ANALYSIS DETAILS ---
    if st.session_state['active_tab'] == "Analysis Details":
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
