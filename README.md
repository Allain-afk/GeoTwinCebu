GeoTwin Cebu — Case 3 (New Project)
==================================

Features
--------
- Layer toggles (QGIS-like overlays): flood hazard, landslide susceptibility, barangays
- Multiple basemaps (OSM + OpenTopoMap)
- AOI inputs: draw polygon, point+buffer, manual technical description parsing
- Output stats + simple interpretation
- Export PDF report (from 2D map viewport + hazard layers)

Run (Windows, Python 3.12)
--------------------------
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cd app
python app.py
Open http://127.0.0.1:5000

Scaling
-------
Add layers in app/geo/sources.py (LAYERS registry). UI + analysis auto-pick them up.
