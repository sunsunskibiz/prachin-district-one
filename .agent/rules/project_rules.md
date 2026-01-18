---
trigger: always_on
description: Project-specific rules for Prachinburi Dashboard
---

# Testing Credentials
When testing the Streamlit application, ALWAYS use the following credentials:
- **Username**: `admin`
- **Password**: `manchongan`

# Development Environment (Ports)
- Use port `8501` by default for the Streamlit server.
- If `8501` is busy, attempt to kill the process first using `pkill -f "streamlit run app.py"`.
- If killing is not possible, try `8502`, then `8503`.

# Architecture & Coding Standards
- **Session State**: Must be initialized at the top of `app.py`. Do not initialize state deep within conditional blocks.
- **Logic Separation**: Keep `app.py` focused on UI/Layout. Complex logic, HTML generation, and data processing must reside in the `utils/` directory. (e.g., `utils/html_utils.py` for tooltips).
- **Performance**: Use `@st.cache_data` for all data loading functions (CSV, KML, GCS downloads) to prevent slow re-runs.

# Specifications & Language
- **UI Language**: All user-facing text (Labels, Buttons, Tooltips) MUST be in **Thai** (TH).
- **Code Language**: All variable names, comments, and logic MUST be in **English** (EN).
- **Fonts**: Prefer using fonts that support Thai characters cleanly (e.g., 'Sarabun' or system sans-serif).
- **Accessibility**: Ensure high contrast for map colors. Tooltips must be provided for all interactive map layers.

# UI Verification
- **Visual Verification Required**: Whenever changes are made to the UI (HTML/CSS/Streamlit layout), you **MUST** run a browser test using the `browser_subagent` to visually verify the changes.
- Do not rely solely on code inspection for UI interactions.