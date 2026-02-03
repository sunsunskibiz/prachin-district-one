import streamlit as st
import pandas as pd
import pydeck as pdk
import logging
import sys

# Import from utils
from utils.constants import CSV_FILE, KML_FILE
from utils.geo_utils import create_mask_polygon, extract_subdistrict_name, extract_amphoe_name
from utils.data_utils import load_comments, load_csv_data, load_kml_data, calculate_votes_by_subdistrict, load_campaign_pins, load_subdistrict_colors
from utils.html_utils import get_subdistrict_tooltip, get_election_html, aggregate_tooltips, create_timeline_html

# --- Logging Config ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger(__name__)

# --- Page Config ---
st.set_page_config(
    page_title="Dashboard of Prachinburi District 1 (Public)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Reuse the create_map_layers logic from app.py (duplicated for standalone safety)
def create_map_layers(
    gdf_districts, subdistrict_colors,
    show_districts, show_winner, show_points, show_campaign_pins, show_comments,
    show_color_orange, show_color_green, show_color_brown, show_color_blue,
    active_uploaded_layers, kml_layers,
    df_map_points, gdf_campaign_pins, df_comments_agg
):
    layers = []

    if show_districts and gdf_districts is not None:
        # 1. Mask Layer
        gdf_mask = create_mask_polygon(gdf_districts)
        if gdf_mask is not None:
             layer_mask = pdk.Layer(
                "GeoJsonLayer",
                gdf_mask,
                id="layer_mask",
                opacity=0.5,
                stroked=False,
                filled=True,
                get_fill_color=[128, 128, 128, 100],
                pickable=False,
            )
             layers.append(layer_mask)

        # 2. Polygon Layer
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
    logger.info("--- Public App Run ---")
    st.title("Dashboard of Prachinburi District 1 (Public View)")

    # Data Loading
    with st.spinner("Loading public data..."):
        df_election = load_csv_data(CSV_FILE).copy()
        gdf_districts = load_kml_data(KML_FILE)
        gdf_campaign_pins = load_campaign_pins()
        
        # Safe handling for campaign pins
        if gdf_campaign_pins is not None and not gdf_campaign_pins.empty:
             gdf_campaign_pins['tooltip_html'] = gdf_campaign_pins['name'].apply(lambda x: f"<b>{x}</b>")
             
        subdistrict_colors = load_subdistrict_colors()
        
        # Load Comments (Read Only)
        comments = load_comments()

    # --- Sidebar Controls ---
    st.sidebar.header("Layer Controls")
    show_districts = st.sidebar.checkbox("แสดงเขตตำบล", value=True)
    show_winner = st.sidebar.checkbox("แสดงเขตผู้ชนะ", value=False)
    show_points = st.sidebar.checkbox("หน่วยเลือกตั้ง", value=True)
    show_campaign_pins = st.sidebar.checkbox("จุดติดป้าย", value=False)
    
    st.sidebar.markdown("**Comment Layers:**")
    show_comments = st.sidebar.checkbox("General Comments", value=True)
    
    st.sidebar.markdown("**Color Highlights:**")
    show_color_orange = st.sidebar.checkbox("เทสีส้ม", value=True)
    show_color_green = st.sidebar.checkbox("เทสีเขียว", value=True)
    show_color_brown = st.sidebar.checkbox("เทสีน้ำตาล", value=True)
    show_color_blue = st.sidebar.checkbox("เทสีฟ้า", value=True)
    
    st.sidebar.markdown("---")
    st.sidebar.header("Map Style")
    map_style_selection = st.sidebar.radio(
        "Select Base Map",
        options=["Satellite", "Default (Light)", "Terrain (ภูมิประเทศ)"],
        index=1
    )
    
    map_styles = {
        "Satellite": "mapbox://styles/mapbox/satellite-v9",
        "Default (Light)": "mapbox://styles/mapbox/light-v9",
        "Terrain (ภูมิประเทศ)": "mapbox://styles/mapbox/outdoors-v12"
    }
    selected_map_style = map_styles.get(map_style_selection, "mapbox://styles/mapbox/light-v9")

    # --- Data Processing for Map ---
    
    # 1. Election Data per District
    df_votes_by_district = pd.DataFrame()
    if not df_election.empty:
        df_votes_by_district = calculate_votes_by_subdistrict(df_election)

    # 2. Process Districts (Colors & Stats)
    if gdf_districts is not None and not gdf_districts.empty:
        gdf_districts['sub_district_name'] = gdf_districts.apply(lambda row: extract_subdistrict_name(row, gdf_districts.columns), axis=1)
        gdf_districts['amphoe_name'] = gdf_districts.apply(lambda row: extract_amphoe_name(row, gdf_districts.columns), axis=1)
        
        if not df_votes_by_district.empty:
            gdf_districts = gdf_districts.merge(
                df_votes_by_district,
                left_on='sub_district_name', 
                right_on='ตำบล', 
                how='inner'
            )
            if 'Winner' in gdf_districts.columns:
                 gdf_districts['Winner'] = gdf_districts['Winner'].fillna("Unknown")
            if 'Winner_Pct' in gdf_districts.columns:
                 gdf_districts['Winner_Pct'] = gdf_districts['Winner_Pct'].fillna(0)
                 
        gdf_districts['tooltip_html'] = gdf_districts.apply(get_subdistrict_tooltip, axis=1)

    # 3. Process Points (Aggregation)
    df_map_points = pd.DataFrame()
    if not df_election.empty:
         df_election['tooltip_html'] = df_election.apply(get_election_html, axis=1)
         df_map_points = df_election.groupby(['latitude', 'longitude'])['tooltip_html'].agg(aggregate_tooltips).reset_index()

    # 4. Process Comments (Timeline)
    df_comments_agg = pd.DataFrame()
    if comments:
        df_raw = pd.DataFrame(comments)
        if 'timestamp' not in df_raw.columns: df_raw['timestamp'] = ''
        if not df_raw.empty:
             df_comments_agg = df_raw.groupby(['latitude', 'longitude']).apply(
                lambda x: pd.Series({
                    'tooltip_html': create_timeline_html(x),
                    'count': len(x)
                })
             ).reset_index()

    # --- Render Map ---
    layers = create_map_layers(
        gdf_districts, subdistrict_colors,
        show_districts, show_winner, show_points, show_campaign_pins, show_comments,
        show_color_orange, show_color_green, show_color_brown, show_color_blue,
        [], {}, # No uploaded layers support for public
        df_map_points, gdf_campaign_pins, df_comments_agg
    )
    
    view_state = pdk.ViewState(latitude=14.0, longitude=101.5, zoom=9)
    
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            map_style=selected_map_style,
            tooltip={"html": "{tooltip_html}", "style": {"color": "white"}}
        ),
        use_container_width=True,
        height=700
    )
    
    st.caption("Public Read-Only View. Login to edit.")

if __name__ == "__main__":
    main()
