
import geopandas as gpd
import pandas as pd
import re

filepath = "แผนที่หาเสียงปราจีนบุรี_fixed.kml"

try:
    print(f"Loading {filepath}...")
    # Attempt to load using the same logic as app.py
    import fiona
    available_layers = fiona.listlayers(filepath)
    print(f"Layers: {available_layers}")
    
    target_layers = ['เส้นแบ่งตำบล ปราจีนบุรี', 'Prachin Buri', 'ปราจีนเขต1', 'เขต 1']
    selected_layer = None
    for target in target_layers:
        if target in available_layers:
            selected_layer = target
            break
    if not selected_layer and available_layers:
        selected_layer = available_layers[0]
    
    gdf = gpd.read_file(filepath, layer=selected_layer)
    print("Columns:", gdf.columns.tolist())
    
    if not gdf.empty:
        # Check description content
        desc_col = next((c for c in gdf.columns if c.lower() == 'description'), None)
        if desc_col:
            print(f"\n--- Sample {desc_col} (First 500 chars) ---")
            sample_desc = str(gdf.iloc[0][desc_col])
            print(sample_desc[:1000])
            
            # Test Regex Extraction
            print("\n--- Regex Test ---")
            
            # Simple regex patterns to find values in the HTML table
            # Pattern usually looks like: <td>T_NAME_T</td> <td>Value</td>
            # Or <td>T_NAME_T</td> ... <td>Value</td>
            
            def extract_val(html, field):
                # Look for the field name followed by some tags and then the value
                # This is a rough guess, will refine after seeing output
                # Try simple key-value table association logic
                match = re.search(rf"{field}</td>\s*<td>(.*?)</td>", html, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                return None

            t_val = extract_val(sample_desc, 'T_NAME_T')
            a_val = extract_val(sample_desc, 'A_NAME_T')
            print(f"Extracted T_NAME_T: '{t_val}'")
            print(f"Extracted A_NAME_T: '{a_val}'")

except Exception as e:
    print(f"Error: {e}")
