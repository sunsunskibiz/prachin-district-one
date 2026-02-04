import os

# Files
CSV_FILE = "คะแนนเลือกตั้ง_ปราจีนบุรี_เขต1_แบ่งเขต.csv"
KML_FILE = "แผนที่หาเสียงปราจีนบุรี.kml"
COLORS_FILE = "subdistrict_colors.json"
VISIT_RECORDS_FILE = "visit_records.json"
COMMENTS_FILE = "comments.csv"
CAMPAIGN_PINS_FILES = ["สถานที่ที่ติดป้ายกำกับ.json", "สถานที่ที่ติดป้ายกำกับ_ปลั้ก.json"]


# Cloud Storage
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "prachin-voter-kml-storage")
