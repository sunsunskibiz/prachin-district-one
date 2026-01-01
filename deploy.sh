#!/bin/bash

# Configuration
PROJECT_ID="prachinburi-district-1"
REGION="asia-southeast1"
SERVICE_NAME="prachin-dashboard"
GCS_BUCKET_NAME="prachin-voter-kml-storage"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment for $SERVICE_NAME to $REGION (Project: $PROJECT_ID)${NC}"

# Check if gcloud is installed locally
if command -v gcloud &> /dev/null; then
    echo -e "${GREEN}Found local gcloud configuration.${NC}"
    echo "This command will prompt for authentication if needed."
    
    # Create bucket if not exists
    echo -e "${GREEN}Ensuring GCS Bucket '$GCS_BUCKET_NAME' exists...${NC}"
    if ! gcloud storage buckets describe "gs://$GCS_BUCKET_NAME" &>/dev/null; then
        echo "Creating bucket..."
        gcloud storage buckets create "gs://$GCS_BUCKET_NAME" --location="$REGION"
    else
        echo "Bucket exists."
    fi

    gcloud run deploy "$SERVICE_NAME" \
        --source . \
        --project "$PROJECT_ID" \
        --region "$REGION" \
        --allow-unauthenticated \
        --set-env-vars GCS_BUCKET_NAME="$GCS_BUCKET_NAME" \
        --memory 2Gi \
        --cpu 2 \
        --port 8501

else
    echo -e "${YELLOW}gcloud command not found locally.${NC}"
    echo -e "${GREEN}Falling back to Dockerized Google Cloud SDK...${NC}"
    
    # Check if docker is available
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed or not in PATH. Please install Docker or gcloud."
        exit 1
    fi

    echo "Launching google/cloud-sdk container..."
    echo "You will be asked to copy a URL to your browser for authentication."
    
    # Run gcloud inside docker
    # We mount the current directory to /app so source code is available
    docker run --rm -it -v "$(pwd):/app" -w /app google/cloud-sdk:alpine /bin/bash -c \
    "echo '${GREEN}Authenticating...${NC}'; \
     gcloud auth login; \
     
     echo ''; \
     echo '${GREEN}Authentication successful.${NC}'; \
     echo '${YELLOW}Listing available projects...${NC}'; \
     gcloud projects list; \
     
     echo ''; \
     echo 'The Project ID you provided earlier was: $PROJECT_ID'; \
     read -p 'Enter the PROJECT_ID you want to use (copy from list above): ' USER_PROJECT_ID; \
     
     if [ -z \"\$USER_PROJECT_ID\" ]; then \
        echo 'Using default/script project ID: $PROJECT_ID'; \
        FINAL_PROJECT_ID=$PROJECT_ID; \
     else \
        FINAL_PROJECT_ID=\$USER_PROJECT_ID; \
     fi; \
     
     echo '${GREEN}Setting project to '\$FINAL_PROJECT_ID'...${NC}'; \
     gcloud config set project \$FINAL_PROJECT_ID; \
     
     echo '${GREEN}Enabling Cloud Run API (just in case)...${NC}'; \
     gcloud services enable run.googleapis.com; \
     gcloud services enable cloudbuild.googleapis.com; \
     
     echo '${GREEN}Fixing IAM Permissions...${NC}'; \
     # Get Project Number
     PROJECT_NUMBER=\$(gcloud projects describe \$FINAL_PROJECT_ID --format='value(projectNumber)'); \
     COMPUTE_SA=\"\${PROJECT_NUMBER}-compute@developer.gserviceaccount.com\"; \
     
     echo \"Granting Storage Admin to \${COMPUTE_SA}...\"; \
     gcloud projects add-iam-policy-binding \$FINAL_PROJECT_ID \
        --member=\"serviceAccount:\${COMPUTE_SA}\" \
        --role=\"roles/storage.admin\"; \
        
     echo \"Granting Cloud Build Builder to \${COMPUTE_SA}...\"; \
     gcloud projects add-iam-policy-binding \$FINAL_PROJECT_ID \
        --member=\"serviceAccount:\${COMPUTE_SA}\" \
        --role=\"roles/cloudbuild.builds.builder\"; \
        
     echo \"Granting Artifact Registry Admin to \${COMPUTE_SA}...\"; \
     gcloud projects add-iam-policy-binding \$FINAL_PROJECT_ID \
        --member=\"serviceAccount:\${COMPUTE_SA}\" \
        --role=\"roles/artifactregistry.admin\"; \
     
     echo '${GREEN}Ensuring GCS Bucket '$GCS_BUCKET_NAME' exists...${NC}'; \
     if ! gcloud storage buckets describe gs://$GCS_BUCKET_NAME &>/dev/null; then \
        echo 'Creating bucket...'; \
        gcloud storage buckets create gs://$GCS_BUCKET_NAME --location=$REGION; \
     else \
        echo 'Bucket exists.'; \
     fi; \
     
     echo '${GREEN}Deploying...${NC}'; \
     gcloud run deploy $SERVICE_NAME \
        --source . \
        --region $REGION \
        --allow-unauthenticated \
        --set-env-vars GCS_BUCKET_NAME=$GCS_BUCKET_NAME \
        --memory 2Gi \
        --cpu 2 \
        --port 8501"
fi
