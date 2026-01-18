---
description: Verify the Prachinburi District Dashboard UI by logging in and taking a screenshot
---

1. Kill any existing Streamlit processes to free up ports and avoid conflicts.
   ```bash
   pkill -f "streamlit run app.py" || true
   ```

2. Install necessary dependencies to ensure the app runs correctly.
   ```bash
   pip install streamlit-authenticator google-cloud-storage
   ```

3. Start the Streamlit application in background mode on port 8501.
   ```bash
   streamlit run app.py --server.port 8501 --server.headless true &
   ```

4. Verify the application using the browser subagent. This will automate the login and checking of the dashboard.
   // turbo
   Use the `browser_subagent` tool with the detailed prompt below:
   "TaskName: Verify Prachinburi Dashboard
    Task:
    1. Navigate to http://localhost:8501
    2. Wait for the login form to appear.
    3. Enter Username: `admin` and Password: `manchongan`.
    4. Click the Login button.
    5. Wait for the header 'Dashboard of Prachinburi District 1' to confirm successful login.
    6. Take a screenshot of the dashboard.
    7. Return the screenshot path."
