---
description: Lock dependencies, build, and deploy the application to Cloud Run
---

1. Safety Check: Verify the application runs locally.
   // turbo
   Run the verification workflow to ensure the app is healthy before deploying.
   ```bash
   # Run the verify_ui workflow
   # (Agent will look up and execute .agent/workflows/verify_ui.md)
   ```

2. Lock Dependencies.
   Ensure `requirements.txt` contains the exact versions currently installed to prevent "it works on my machine" issues in the cloud.
   ```bash
   pip freeze > requirements.txt
   ```

3. Authenticate and Deploy.
   Execute the deployment script.
   **Note**: Ensure Docker is running if you don't have `gcloud` installed locally.
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

4. Verify Deployment.
   After the script finishes, it will output a service URL.
   Visit that URL to confirm the cloud instance is running correctly.
