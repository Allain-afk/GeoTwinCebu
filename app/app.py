from __future__ import annotations

import json
import os
from pathlib import Path

# Load .env when running locally (no-op in Vercel where env vars are set via dashboard)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify

from geo.sources import LAYERS, BASEMAPS, fetch_layer_geojson, clear_cache_if_requested
from geo.boundary import parse_aoi, parse_manual_vertices_text, parse_coords_csv_text, parse_traverse_text
from geo.analysis import check_hazard_at_point
from geo.routing import (
    find_nearest_centers,
    get_osrm_route,
    format_duration,
    format_distance,
    google_maps_directions_url,
)

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / "data_cache"
DATA_DIR = APP_DIR / "data"

for p in (CACHE_DIR,):
    p.mkdir(exist_ok=True)

# Load evacuation centers once at startup
CENTERS_FC = json.loads((DATA_DIR / "evacuation_centers.geojson").read_text(encoding="utf-8"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html", layers=LAYERS, basemaps=BASEMAPS)


# ── API: metadata ─────────────────────────────────────────────────────────────

@app.get("/api/metadata")
def api_metadata():
    return jsonify({"ok": True, "layers": {k: {
        "title": v["title"],
        "kind": v["kind"],
        "style": v.get("style", {}),
        "legend": v.get("legend", ""),
    } for k, v in LAYERS.items()}, "basemaps": BASEMAPS})


# ── API: evacuation centers ───────────────────────────────────────────────────

@app.get("/api/evacuation-centers")
def api_evacuation_centers():
    return jsonify(CENTERS_FC)


# ── API: boundary parsing (kept for manual input) ─────────────────────────────

@app.post("/api/parse-boundary")
def api_parse_boundary():
    payload = request.get_json(force=True)
    mode = payload.get("mode")
    text = (payload.get("text") or "").strip()
    crs = (payload.get("crs") or "EPSG:4326").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text provided."}), 400

    if mode == "manual_vertices":
        geom, qa = parse_manual_vertices_text(text, crs=crs)
    elif mode == "coords_csv":
        geom, qa = parse_coords_csv_text(text, crs=crs)
    elif mode == "traverse":
        geom, qa = parse_traverse_text(text, crs=crs)
    else:
        return jsonify({"ok": False, "error": "Invalid mode."}), 400

    return jsonify({"ok": True, "geometry": geom, "qa": qa})


# ── API: route finder ─────────────────────────────────────────────────────────

@app.post("/api/route")
def api_route():
    payload = request.get_json(force=True)

    user_lat = payload.get("lat")
    user_lon = payload.get("lon")
    if user_lat is None or user_lon is None:
        return jsonify({"ok": False, "error": "lat and lon are required."}), 400

    user_lat = float(user_lat)
    user_lon = float(user_lon)

    # Optional: pre-load hazard layers for context warnings
    active_layers = payload.get("active_layers") or []
    options = payload.get("options") or {}
    clear_cache_if_requested(CACHE_DIR, options)

    hazard_cache = {}
    for lid in active_layers:
        # Use a large bbox around the user point for hazard check
        from shapely.geometry import Point
        from shapely.ops import transform as shp_transform
        from pyproj import Transformer
        fwd = Transformer.from_crs("EPSG:4326", "EPSG:3124", always_xy=True)
        inv = Transformer.from_crs("EPSG:3124", "EPSG:4326", always_xy=True)
        px, py = fwd.transform(user_lon, user_lat)
        buf_m = 2000  # 2 km search radius for hazard context
        buf = Point(px, py).buffer(buf_m)
        aoi = shp_transform(lambda x, y, z=None: inv.transform(x, y), buf)
        fc = fetch_layer_geojson(layer_id=lid, cache_dir=CACHE_DIR, aoi=aoi)
        if fc:
            hazard_cache[lid] = fc

    # Hazard warnings at user location
    hazard_warnings = check_hazard_at_point(user_lat, user_lon, hazard_cache)

    # Find nearest centers
    nearest = find_nearest_centers(user_lat, user_lon, CENTERS_FC, top_n=3)
    if not nearest:
        return jsonify({"ok": False, "error": "No evacuation centers found."}), 500

    best = nearest[0]
    center_feat = best["feature"]
    center_props = center_feat["properties"]
    c_lon, c_lat = center_feat["geometry"]["coordinates"]

    # Get road route
    route_data = get_osrm_route(user_lat, user_lon, c_lat, c_lon)

    # Hazard warning at destination
    dest_warnings = check_hazard_at_point(c_lat, c_lon, hazard_cache)
    if dest_warnings:
        hazard_warnings.append("ℹ️ The evacuation center may also be near a hazard zone — follow official instructions.")

    gmaps_url = google_maps_directions_url(user_lat, user_lon, c_lat, c_lon)

    # Build alternatives list (without full routes, just names + distances)
    alternatives = []
    for item in nearest[1:]:
        fp = item["feature"]["properties"]
        alternatives.append({
            "name": fp["name"],
            "type": fp["type"],
            "barangay": fp.get("barangay", ""),
            "distance_m": round(item["distance_m"]),
            "distance_label": format_distance(item["distance_m"]),
        })

    return jsonify({
        "ok": True,
        "center": {
            "name": center_props["name"],
            "type": center_props["type"],
            "barangay": center_props.get("barangay", ""),
            "capacity": center_props.get("capacity"),
            "notes": center_props.get("notes", ""),
            "lat": c_lat,
            "lon": c_lon,
        },
        "route": route_data["route_geojson"],
        "distance_m": round(route_data["distance_m"]),
        "distance_label": format_distance(route_data["distance_m"]),
        "duration_label": format_duration(route_data["duration_s"]),
        "route_source": route_data["source"],
        "google_maps_url": gmaps_url,
        "hazard_warnings": hazard_warnings,
        "alternatives": alternatives,
    })


# ── API: hazard layer GeoJSON (for map overlay) ───────────────────────────────

@app.post("/api/layer-geojson")
def api_layer_geojson():
    """Fetch a single hazard layer for the current map viewport bbox."""
    payload = request.get_json(force=True)
    layer_id = payload.get("layer_id")
    bbox = payload.get("bbox")  # [minLon, minLat, maxLon, maxLat]
    if not layer_id or not bbox or len(bbox) != 4:
        return jsonify({"ok": False, "error": "layer_id and bbox[4] required"}), 400

    from shapely.geometry import box
    aoi = box(bbox[0], bbox[1], bbox[2], bbox[3])
    options = payload.get("options") or {}
    clear_cache_if_requested(CACHE_DIR, options)
    fc = fetch_layer_geojson(layer_id=layer_id, cache_dir=CACHE_DIR, aoi=aoi)
    if fc is None:
        return jsonify({"ok": False, "error": "Layer not found."}), 404
    return jsonify({"ok": True, "geojson": fc})


if __name__ == "__main__":
    app.run(debug=True)
