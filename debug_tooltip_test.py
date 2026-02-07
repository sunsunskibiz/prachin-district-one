import pandas as pd
import sys
import os

# Add root to sys.path to allow imports if needed, but we just need pandas here
sys.path.append(os.getcwd())

from utils.constants import CSV_FILE

print(f"Reading {CSV_FILE}...")
try:
    df = pd.read_csv(CSV_FILE)
    print("Columns:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict())

    # Check for latitude/longitude
    if "latitude" in df.columns and "longitude" in df.columns:
        print("Latitude/Longitude columns found.")
        print(
            f"Sample Lat: {df.iloc[0]['latitude']} (Type: {type(df.iloc[0]['latitude'])})"
        )
    else:
        print("MISSING latitude/longitude columns!")

    # Test get_election_html logic locally
    from utils.html_utils import get_election_html

    html = get_election_html(df.iloc[0])
    print("\nGenerated HTML for first row:")
    print(html)

    if "maps/search" in html:
        print("\nSUCCESS: Google Maps link detected in HTML.")
    else:
        print("\nFAILURE: Google Maps link NOT found in HTML.")

except Exception as e:
    print(f"Error: {e}")
