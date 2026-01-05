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

@st.cache_data(show_spinner=False)
def process_path_overlaps(_layers: list, layer_names: list) -> Optional[gpd.GeoDataFrame]:
    """
    Combines segments from multiple KML layers and counts overlaps.
    Uses grid snapping to detect overlaps and linemerge for smooth rendering.
    Cached for performance (hashes 'layer_names', ignores '_layers').
    """
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import linemerge
    from collections import Counter
    import math

    if not _layers:
        return None
        
    all_segments = []
    
    
    # Tolerances
    # Relaxed to reduce vertex count (approx 55m grid)
    SNAP_GRID = 0.0005 
    DENSIFY_LEN = 0.001
    
    # print(f"DEBUG: Processing {len(_layers)} layers (Grid: {SNAP_GRID})...") # Reduced log spam

    for gdf in _layers:
        if gdf is None or gdf.empty:
            continue
            
        # Iterate over features
        for geom in gdf.geometry:
            if geom is None:
                continue

            # Helper to process coordinate sequence
            def process_coords(coords):
                if not coords or len(coords) < 2:
                    return

                # 1. Densify
                densified = [coords[0]]
                for i in range(len(coords) - 1):
                    p1 = coords[i]
                    p2 = coords[i+1]
                    dist = math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                    
                    if dist > DENSIFY_LEN:
                        num_segments = int(dist // DENSIFY_LEN) + 1
                        for j in range(1, num_segments):
                            frac = j / num_segments
                            nx = p1[0] + (p2[0] - p1[0]) * frac
                            ny = p1[1] + (p2[1] - p1[1]) * frac
                            densified.append((nx, ny))
                    densified.append(p2)
                
                # 2. Snap to Custom Grid
                def snap(val):
                    return round(val / SNAP_GRID) * SNAP_GRID

                for i in range(len(densified) - 1):
                    p1 = densified[i]
                    p2 = densified[i+1]
                    
                    p1_s = (snap(p1[0]), snap(p1[1]))
                    p2_s = (snap(p2[0]), snap(p2[1]))
                    
                    if p1_s == p2_s: continue 
                    
                    # Sort to handle direction
                    seg = tuple(sorted((p1_s, p2_s)))
                    all_segments.append(seg)

            if geom.geom_type == 'LineString':
                process_coords(list(geom.coords))
            elif geom.geom_type == 'MultiLineString':
                for line in geom.geoms:
                    process_coords(list(line.coords))
            elif geom.geom_type == 'GeometryCollection':
                # Recursive handling for GeometryCollection
                def process_collection(collection):
                    for sub_geom in collection.geoms:
                        if sub_geom.geom_type == 'LineString':
                            process_coords(list(sub_geom.coords))
                        elif sub_geom.geom_type == 'MultiLineString':
                            for line in sub_geom.geoms:
                                process_coords(list(line.coords))
                        elif sub_geom.geom_type == 'GeometryCollection':
                            process_collection(sub_geom)
                process_collection(geom)
                    
    if not all_segments:
        return None
        
    # Count occurrences
    counts = Counter(all_segments)
    
    # Group by count to merge lines
    segments_by_count = {}
    for seg, count in counts.items():
        if count not in segments_by_count:
            segments_by_count[count] = []
        segments_by_count[count].append(LineString(seg))
        
    final_data = []
    
    # 3. Merge Segments for Smoothness
    for count, lines in segments_by_count.items():
        merged = linemerge(lines)
        if merged.geom_type == 'LineString':
            final_data.append({'geometry': merged, 'overlap_count': count})
        elif merged.geom_type == 'MultiLineString':
            for part in merged.geoms:
                 final_data.append({'geometry': part, 'overlap_count': count})
        
    gdf_result = gpd.GeoDataFrame(final_data)
    
    # Assign Colors 
    def get_color(count):
        if count == 1:
            return [255, 80, 0, 255]   # Orange
        elif count == 2:
            return [0, 255, 0, 255]    # Green
        else:
            return [0, 0, 255, 255]    # Blue
            
    gdf_result['color'] = gdf_result['overlap_count'].apply(get_color)
    
    # print(f"DEBUG: Smooth Lines Generated: {len(gdf_result)} features")
    return gdf_result
