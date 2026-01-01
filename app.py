import streamlit as st
import pandas as pd
import pydeck as pdk
import time
import logging
import sys
import os

# Import from new utils
from utils.constants import CSV_FILE, KML_FILE, GCS_BUCKET_NAME
from utils.geo_utils import create_mask_polygon, extract_subdistrict_name, extract_amphoe_name
from utils.data_utils import load_comments, save_comment, load_csv_data, load_kml_data, calculate_votes_by_subdistrict
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

# --- Heartbeat Debug ---
st.sidebar.markdown(f"**Server Time:** `{time.strftime('%H:%M:%S')}`")
if 'init_time' not in st.session_state:
    st.session_state['init_time'] = time.time()
st.sidebar.caption(f"Session Age: {int(time.time() - st.session_state['init_time'])}s")

def main():
    st.title("Dashboard of Prachinburi District 1")
    
    # Load Data
    with st.spinner("Loading data..."):
        df_election = load_csv_data(CSV_FILE)
        
        # Always load default districts
        gdf_districts = load_kml_data(KML_FILE)

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
             # Auto-Process Logic
             file_id = f"{uploaded_kml.name}_{uploaded_kml.size}"
             
             if file_id not in st.session_state.get('processed_uploads', []):
                 if 'processed_uploads' not in st.session_state: st.session_state['processed_uploads'] = []
                 
                 st.sidebar.info(f"Processing {uploaded_kml.name}...")
                 safe_name = uploaded_kml.name.replace(" ", "_")
                 
                 # 1. Determine Environment (Cloud vs Local)
                 client = get_gcs_client()
                 
                 if client:
                     # --- CLOUD MODE (GCS) ---
                     success = upload_to_gcs(uploaded_kml, GCS_BUCKET_NAME, safe_name)
                     if success:
                         st.sidebar.success(f"☁️ Uploaded to GCS!")
                         # Auto-Visualize
                         try:
                             gdf_new = load_kml_from_gcs(GCS_BUCKET_NAME, safe_name)
                             if gdf_new is not None and not gdf_new.empty:
                                 st.session_state['kml_layers'][safe_name] = gdf_new
                                 st.success(f"✅ Visualized: {safe_name}")
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
                     try:
                         # Save to temp for processing
                         temp_path = os.path.join("/tmp", safe_name)
                         with open(temp_path, "wb") as f:
                             f.write(uploaded_kml.getbuffer())
                             
                         # Parse directly
                         st.sidebar.info("Parsing locally...")
                         gdf_new = load_kml_data(temp_path)
                         if gdf_new is not None and not gdf_new.empty:
                             st.session_state['kml_layers'][safe_name] = gdf_new
                             st.sidebar.success(f"🏠 Loaded locally: {safe_name}")
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
