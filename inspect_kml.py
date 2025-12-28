
import geopandas as gpd
import fiona

filepath = "แผนที่หาเสียงปราจีนบุรี_fixed.kml"

try:
    # Mimic the loading logic in app.py to see exactly what we get
    target_layers = ['เส้นแบ่งตำบล ปราจีนบุรี', 'Prachin Buri', 'ปราจีนเขต1', 'เขต 1']
    available_layers = fiona.listlayers(filepath)
    print(f"Available layers: {available_layers}")
    
    selected_layer = None
    for target in target_layers:
        if target in available_layers:
            selected_layer = target
            break
    if not selected_layer and available_layers:
        selected_layer = available_layers[0]
        
    print(f"Loading layer: {selected_layer}")
    gdf = gpd.read_file(filepath, layer=selected_layer)
    print("Columns:", gdf.columns.tolist())
    if not gdf.empty:
        print("First row sample:", gdf.iloc[0].to_dict())

except Exception as e:
    print(e)
