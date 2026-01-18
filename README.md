# Prachinburi District 1 Dashboard

A comprehensive Streamlit-based dashboard for visualizing election data, managing campaign points, and analyzing voter demographics in Prachinburi District 1.

## Features

- **Interactive Maps**: High-performance visualizations using PyDeck and Folium (via Streamlit) to display district boundaries, election units, and campaign locations.
- **Layer Management**: Toggle efficient layers including:
  - **Districts**: View sub-district boundaries with auto-masking of outside areas.
  - **Winners**: Visualize election winners by party colors (Bhumjaithai, Move Forward, Pheu Thai).
  - **Points**: Precise locations of election units.
  - **Campaign Pins**: 3D column visualization of campaign poster locations.
  - **Comments**: Geolocation-based comments for field notes.
- **KML Integration**: Upload and visualize custom KML files directly on the map. Supports Google Cloud Storage (GCS) for persistence.
- **Color Assignment**: interactive tool to assign and visualize specific colors (Orange, Green, Brown, Blue) to sub-districts for strategic planning.
- **Comment System**: Add, view, and delete comments pinned to specific coordinates or districts.
- **Authentication**: Secure login system to protect sensitive data.

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd prachin-district-one
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuration:**
   - Ensure `auth_config.yaml` is present for authentication settings.
   - Place necessary data files (CSV, KML, JSON) in the root or `data/` directory as referenced in `utils/constants.py`.

## Usage

Run the Streamlit application:

```bash
streamlit run app.py
```

The application will default to port **8501**. Open your browser to `http://localhost:8501`.

**Default Credentials (for testing):**
- **Username:** `admin`
- **Password:** `manchongan`

## Project Structure

```
├── app.py                  # Main application entry point
├── utils/                  # Utility modules
│   ├── constants.py        # File paths and configuration constants
│   ├── data_utils.py       # Data loading and processing functions
│   ├── geo_utils.py        # Geospatial operations (polygons, masks)
│   ├── gcs_utils.py        # Google Cloud Storage integration
│   └── html_utils.py       # HTML generation for tooltips
├── auth_config.yaml        # Authentication configuration
├── requirements.txt        # Python dependencies
├── deploy.sh               # Deployment script
├── Dockerfile              # Container configuration
└── README.md               # Project documentation
```

## Deployment

The project includes a `Dockerfile` and `deploy.sh` for easy deployment to platforms like Google Cloud Run.

```bash
# Example deployment
./deploy.sh
```

## Technologies

- **Python 3.9+**
- **Streamlit**: Web framework
- **PyDeck**: WebGL-powered map visualizations
- **Pandas / GeoPandas**: Data manipulation
- **Google Cloud Storage**: specific integrations