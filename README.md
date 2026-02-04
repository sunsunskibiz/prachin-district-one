# Prachinburi District 1 Dashboard

A comprehensive Streamlit-based dashboard for visualizing election data, managing campaign points, and analyzing voter demographics in Prachinburi District 1.

## Features

- **Public Read-Only Mode**: A dedicated, simplified view for public access (`public_app.py`) with:
- **Interactive Maps**: High-performance visualizations using PyDeck and Folium (via Streamlit) to display district boundaries, election units, and campaign locations.
- **Layer Management**: Toggle efficient layers including:
  - **Winners**: Visualize election winners by party colors (Bhumjaithai, Move Forward, Pheu Thai).
  - **Points**: Precise locations of election units.
  - **Campaign Pins**: 3D column visualization of campaign poster locations.
  - **Comments**: Geolocation-based comments for field notes.
- **KML Integration**: Upload and visualize custom KML files directly on the map. Supports Google Cloud Storage (GCS) for persistence.
- **Color Assignment**: interactive tool to assign and visualize specific colors (Orange, Green, Brown, Blue) to sub-districts for strategic planning.
- **Comment System**: Add, view, and delete comments pinned to specific coordinates or districts.
- **Visit Record**: Add the visit date to each sub-districts.
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

### Public App (Read-Only)

Run the public-facing application:

```bash
streamlit run public_app.py
```

Access at `http://localhost:8501`.

### Admin Dashboard (Full Access)

Run the main authenticated application:

```bash
streamlit run app.py
```

Access at `http://localhost:8502` (if configured) or default port.

## Project Structure

```
├── app.py                  # Main authenticated application
├── public_app.py           # Public read-only application
├── utils/                  # Utility modules
│   ├── constants.py        # File paths and configuration constants
│   ├── data_utils.py       # Data loading and processing functions
│   ├── geo_utils.py        # Geospatial operations (polygons, masks)
│   ├── gcs_utils.py        # Google Cloud Storage integration
│   └── html_utils.py       # HTML generation for tooltips (Thai formatting support)
├── auth_config.yaml        # Authentication configuration
├── requirements.txt        # Python dependencies
├── deploy.sh               # Deployment script
├── deploy_public.sh        # Public app deployment script
├── Dockerfile              # Container configuration
└── README.md               # Project documentation
```

## Deployment

The project includes Docker support and deployment scripts:

- `deploy.sh`: Deploys the main admin dashboard.
- `deploy_public.sh`: Deploys the public read-only app.

```bash
# Example deployment
./deploy_public.sh
```

## Technologies

- **Python 3.9+**
- **Streamlit**: Web framework
- **PyDeck**: WebGL-powered map visualizations
- **Pandas / GeoPandas**: Data manipulation
- **Google Cloud Storage**: Persistence layer
