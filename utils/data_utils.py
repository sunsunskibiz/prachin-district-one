import streamlit as st
import pandas as pd
import geopandas as gpd
from fastkml import kml
from typing import Optional
import os
from .constants import COMMENTS_FILE

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
