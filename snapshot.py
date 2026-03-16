import os
import time
import json
from playwright.sync_api import sync_playwright

ASSET_DIR = "/Users/sunsun/Library/CloudStorage/GoogleDrive-chantapat.sun@gmail.com/My Drive/Voter/prachin-district-one/presentation_assets"

def inject_data_and_reload():
    color_file = "subdistrict_colors.json"
    visit_file = "visit_records.json"

    # Inject some colors
    colors = {
        "ดงพระราม": "green",
        "บางบริบูรณ์": "orange",
        "ท่างาม": "brown",
        "บางเดชะ": "blue",
        "บ้านทาม": "orange",
        "ท่าตูม": "green",
        "ศรีมหาโพธิ": "blue",
        "หนองโพรง": "brown",
        "โคกปีบ": "orange",
        "หนองช้างแล่น": "blue"
    }
    with open(color_file, "w") as f:
        json.dump(colors, f, ensure_ascii=False)

    # Inject some visits
    import datetime
    today = datetime.date.today().strftime("%Y-%m-%d")
    visits = {
        "ดงพระราม": [{"date": today, "note": "Visited community center"}],
        "บ้านทาม": [
            {"date": today, "note": "Meeting local leaders"},
            {"date": "2026-03-10", "note": "Previous check"},
            {"date": "2026-03-05", "note": "Initial planning"},
            {"date": "2026-03-01", "note": "First contact"}
        ],
        "หนองโพรง": [{"date": "2026-03-12", "note": "Follow up"}, {"date": "2026-03-14", "note": "Second follow up"}],
        "ท่าตูม": [{"date": "2026-03-15", "note": "Door-to-door check"}],
        "ศรีมหาโพธิ": [{"date": "2026-03-11", "note": "City hall visit"}, {"date": "2026-03-01", "note": "Met mayor"}],
        "โคกปีบ": [{"date": "2026-02-28", "note": "Event"}, {"date": "2026-03-02", "note": "Followup"}, {"date": "2026-03-05", "note": "Another event"}, {"date": "2026-03-10", "note": "Visit 4"}]

    }
    with open(visit_file, "w") as f:
        json.dump(visits, f, ensure_ascii=False)

def main():
    # Inject data so streamlit reloads it
    inject_data_and_reload()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a slightly wider viewport to ensure map looks good
        context = browser.new_context(viewport={'width': 1400, 'height': 850})
        page = context.new_page()

        # Login
        page.goto("http://localhost:8501")
        time.sleep(2)
        
        # Login
        page.fill("input[type='text']", "admin")
        page.fill("input[type='password']", "manchongan")
        page.locator('button', has_text='Login').click()
        
        # Wait for login to complete
        page.wait_for_selector('text=USER:', timeout=10000)
        time.sleep(4) # Map takes time to render

        # 1. Color Assign Screenshot
        page.locator('label', has_text='Color Assign').click()
        time.sleep(6) # Wait for map to re-render
        
        # Taking screenshot
        page.screenshot(path=os.path.join(ASSET_DIR, "color_assign.png"))

        # 2. Visit Record Screenshot
        page.locator('label', has_text='Visit Record').click()
        time.sleep(6) # Wait for map to re-render
        
        # Taking screenshot
        page.screenshot(path=os.path.join(ASSET_DIR, "visit_record.png"))
        
        browser.close()

if __name__ == "__main__":
    main()
