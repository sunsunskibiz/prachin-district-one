
import sys
import os
import geopandas as gpd

# Add current directory to path so we can import utils
sys.path.append(os.getcwd())

from utils.data_utils import load_kml_data

kml_path = "/Users/sunsun/Library/CloudStorage/GoogleDrive-chantapat.sun@gmail.com/My Drive/Voter/prachin-district-one/30-12-2025-2.kml"

print(f"Loading {kml_path}...")
gdf = load_kml_data(kml_path)

if gdf is not None:
    print(f"Loaded {len(gdf)} features.")
    print("Geometry Types found:")
    for idx, geom in enumerate(gdf.geometry):
        print(f"Feature {idx}: {geom.geom_type}")
        if geom.geom_type == 'GeometryCollection':
            print("  Contents of GeometryCollection:")
            for sub_geom in geom.geoms:
                print(f"    - {sub_geom.geom_type}")
else:
    print("Failed to load KML.")
