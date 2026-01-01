import streamlit as st
import os
import logging
from google.cloud import storage
from .data_utils import load_kml_data

logger = logging.getLogger(__name__)

@st.cache_resource
def get_gcs_client():
    try:
        from google.auth.exceptions import DefaultCredentialsError
        client = storage.Client()
        return client
    except Exception as e:
        # Don't spam error here, just return None. The caller will handle fallback.
        logger.warning(f"GCS Client not available (likely local mode): {e}")
        return None

def list_gcs_kml_files(bucket_name):
    """Lists all KML files in the bucket."""
    logger.info(f"Listing files in bucket: {bucket_name}")
    client = get_gcs_client()
    if not client: return []
    try:
        bucket = client.bucket(bucket_name)
        blobs = list(bucket.list_blobs()) # Force iteration to check connectivity
        kml_files = [blob.name for blob in blobs if blob.name.lower().endswith('.kml')]
        logger.info(f"Found {len(kml_files)} KML files: {kml_files}")
        return kml_files
    except Exception as e:
        logger.error(f"Error listing GCS files: {e}")
        st.sidebar.error(f"Error listing GCS files: {e}")
        return []

def upload_to_gcs(file_obj, bucket_name, destination_blob_name):
    """Uploads a file object to the bucket OR local temp if GCS unavailable."""
    logger.info(f"Attempting to upload {destination_blob_name}...")
    client = get_gcs_client()
    
    # --- LOCAL FALLBACK ---
    if not client:
        logger.info("GCS unavailable. Using local temporary storage.")
        local_dir = "/tmp/local_uploads"
        if not os.path.exists(local_dir):
            os.makedirs(local_dir)
        
        local_path = os.path.join(local_dir, destination_blob_name)
        try:
            with open(local_path, "wb") as f:
                f.write(file_obj.getvalue())
            logger.info(f"Saved locally to {local_path}")
            return True
        except Exception as e:
            st.error(f"Local save failed: {e}")
            return False
    # ----------------------

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        
        # Read bytes from Streamlit UploadedFile
        data = file_obj.getvalue()
        blob.upload_from_string(data, content_type='application/vnd.google-earth.kml+xml')
        
        logger.info(f"Successfully uploaded {destination_blob_name} to GCS (Size: {len(data)} bytes).")
        return True
    except Exception as e:
        logger.error(f"Error uploading to GCS: {e}")
        st.sidebar.error(f"Error uploading to GCS: {e}")
        return False

def load_kml_from_gcs(bucket_name, blob_name):
    """Downloads KML from GCS (or local temp) to a temp file and queues it for loading."""
    logger.info(f"Loading {blob_name}...")
    client = get_gcs_client()
    
    # --- LOCAL FALLBACK ---
    if not client:
        local_path = os.path.join("/tmp/local_uploads", blob_name)
        if os.path.exists(local_path):
             logger.info(f"Loading from local path: {local_path}")
             return load_kml_data(local_path)
        else:
             st.error(f"Local file not found: {local_path}")
             return None
    # ----------------------

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        temp_filename = f"/tmp/temp_gcs_{blob_name}"
        blob.download_to_filename(temp_filename)
        logger.info(f"Downloaded {blob_name} to {temp_filename}")
        
        gdf = load_kml_data(temp_filename)
        
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
        return gdf
    except Exception as e:
        logger.error(f"Error loading {blob_name} from GCS: {e}")
        st.error(f"Error loading {blob_name} from GCS: {e}")
        return None
