import geopandas as gpd
import re
import streamlit as st
from typing import Optional

def create_mask_polygon(gdf: gpd.GeoDataFrame) -> Optional[gpd.GeoDataFrame]:
    """Creates a polygon covering the area OUTSIDE the given GeoDataFrame."""
    if gdf is None or gdf.empty:
        return None
    
    # Check if we have polygons.
    has_polygons = any(geom.geom_type in ('Polygon', 'MultiPolygon') for geom in gdf.geometry)
    if not has_polygons:
        return None

    try:
        from shapely.geometry import box
        
        # Create a large bounding box (covering the world)
        world_box = box(-180, -90, 180, 90)
        
        # Merge all districts into one shape
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
