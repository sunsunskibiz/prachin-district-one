import os

# Files
CSV_FILE = "คะแนนเลือกตั้ง_ปราจีนบุรี_เขต1_แบ่งเขต.csv"
KML_FILE = "แผนที่หาเสียงปราจีนบุรี.kml"
COMMENTS_FILE = "comments.csv"

# Cloud Storage
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "prachin-voter-kml-storage")
