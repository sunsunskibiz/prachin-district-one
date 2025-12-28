import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
from fastkml import kml
from typing import Optional
import os
import re

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
    
    try:
        from shapely.geometry import box
        
        # Create a large bounding box (covering the world or a sufficient area)
        # Prachinburi is around 101 E, 14 N. 
        # A box covering Thailand/SEA should be enough + margin. 
        # Or just global [-180, -90, 180, 90]
        world_box = box(97.0, 5.0, 106.0, 21.0) # Approx Thailand bounds (easier to render than whole world sometimes)
        # Actually Pydeck handles global fine, but let's stick to a reasonable bound around the data to avoid artifacts
        # Using the bounds of the gdf + buffer is safer?
        # User wants "gray out the area that not in the blue polygon".
        # Usually implies the rest of the map.
        # Let's use a very large box.
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


# --- Main App ---

def main():
    st.title("Dashboard of Prachinburi District 1")
    
    # Load Data
    with st.spinner("Loading data..."):
        df_election = load_csv_data(CSV_FILE)
        gdf_districts = load_kml_data(KML_FILE)
    
    # Inspect Data (Debug mode or just simple check)
    # st.write(df_election.head())
    
    if gdf_districts is not None and not gdf_districts.empty:
        st.sidebar.success(f"Loaded {len(gdf_districts)} polygons from KML")
        
        # Helper to safely get KML columns
        # KML usually loads with 'Name' and 'Description' (often containing HTML table of attributes)
        # We need to parse 'T_NAME_T' and 'A_NAME_T' from that Description HTML if they aren't columns.
        
        kml_cols = gdf_districts.columns
        name_col = next((c for c in kml_cols if c.lower() == 'name'), None)
        desc_col = next((c for c in kml_cols if c.lower() == 'description'), None)
        
        def get_kml_html(row):
            # 1. Try direct column access (if geopandas loaded it nicely)
            t_val = row.get('T_NAME_T', None)
            a_val = row.get('A_NAME_T', None)
            
            # 2. If not found, try parsing 'description' (fallback or fastkml result)
            desc_html = str(row[desc_col]) if desc_col else ""
            
            if not t_val and desc_html:
                # Regex to find: <td>T_NAME_T</td><td>Value</td> or similar
                # Handling flexible whitespace and casing
                match = re.search(r"<td>T_NAME_T</td>\s*<td>(.*?)</td>", desc_html, re.IGNORECASE)
                if match:
                    t_val = match.group(1).strip()
            
            if not a_val and desc_html:
                match = re.search(r"<td>A_NAME_T</td>\s*<td>(.*?)</td>", desc_html, re.IGNORECASE)
                if match:
                    a_val = match.group(1).strip()
            
            # Default fallbacks if extraction failed
            title = t_val if t_val else (row[name_col] if name_col else "Sub-district")
            body = a_val if a_val else ""
            
            return f"<b>ต.{title}</b><br/>อ.{body}"
        
        gdf_districts['tooltip_html'] = gdf_districts.apply(get_kml_html, axis=1)

    else:
        st.sidebar.warning("Failed to load KML polygons")

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
    show_points = st.sidebar.checkbox("Show Election Points (CSV)", value=True)
    
    st.sidebar.markdown("---")
    st.sidebar.header("Map Style")
    map_style_selection = st.sidebar.radio(
        "Select Base Map",
        options=["Satellite", "Default (Light)"],
        index=1
    )
    
    # Map Style Mapping
    map_styles = {
        "Satellite": "mapbox://styles/mapbox/satellite-v9",
        "Default (Light)": "mapbox://styles/mapbox/light-v9"
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
        # Polygon Layer - Blue Lines Style (Requested)
        layer_districts = pdk.Layer(
            "GeoJsonLayer",
            gdf_districts,
            opacity=1.0,
            stroked=True,
            filled=True, 
            get_fill_color=[0, 0, 0, 0], 
            get_line_color=[0, 0, 255, 255], # Blue lines
            get_line_width=30,
            pickable=True,
            auto_highlight=True,
            wireframe=True,
            highlight_color=[0, 0, 255, 128], # Blue highlight
        )
        layers.append(layer_districts)

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
        initial_view_state = pdk.ViewState(
            latitude=df_election['latitude'].mean(),
            longitude=df_election['longitude'].mean(),
            zoom=10,
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

if __name__ == "__main__":
    main()
