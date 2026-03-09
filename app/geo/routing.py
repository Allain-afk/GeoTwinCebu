from __future__ import annotations

import math
from typing import Optional, Tuple, Dict, Any

import requests
from shapely.geometry import Point, shape, mapping
from shapely.ops import transform
from pyproj import Transformer

OSRM_BASE = "http://router.project-osrm.org/route/v1/driving"
WGS84 = "EPSG:4326"
PRS92_ZONE4 = "EPSG:3124"

# ── distance helpers ──────────────────────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in metres between two WGS84 points."""
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# ── nearest center ────────────────────────────────────────────────────────────

def find_nearest_centers(
    user_lat: float,
    user_lon: float,
    centers_fc: dict,
    top_n: int = 3,
) -> list[Dict[str, Any]]:
    """Return the `top_n` closest evacuation centers sorted by straight-line distance."""
    results = []
    for feat in centers_fc.get("features", []):
        coords = feat["geometry"]["coordinates"]  # [lon, lat]
        c_lon, c_lat = coords[0], coords[1]
        dist = haversine_m(user_lat, user_lon, c_lat, c_lon)
        results.append({"feature": feat, "distance_m": dist})
    results.sort(key=lambda x: x["distance_m"])
    return results[:top_n]


# ── OSRM routing ──────────────────────────────────────────────────────────────

def get_osrm_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Call the public OSRM demo server.
    Returns dict with keys: route_geojson, distance_m, duration_s, source.
    Falls back to straight-line on failure.
    """
    url = f"{OSRM_BASE}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                return {
                    "route_geojson": {
                        "type": "Feature",
                        "geometry": route["geometry"],
                        "properties": {},
                    },
                    "distance_m": route["distance"],
                    "duration_s": route["duration"],
                    "source": "osrm",
                }
    except Exception:
        pass

    # Fallback: straight-line
    return _straight_line_route(origin_lat, origin_lon, dest_lat, dest_lon)


def _straight_line_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> Dict[str, Any]:
    dist = haversine_m(origin_lat, origin_lon, dest_lat, dest_lon)
    # Estimate walking speed ~5 km/h
    duration_s = (dist / 5000) * 3600
    return {
        "route_geojson": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [origin_lon, origin_lat],
                    [dest_lon, dest_lat],
                ],
            },
            "properties": {},
        },
        "distance_m": dist,
        "duration_s": duration_s,
        "source": "straight_line",
    }


# ── travel time formatting ────────────────────────────────────────────────────

def format_duration(duration_s: float) -> str:
    """Human-readable duration string."""
    mins = int(duration_s / 60)
    if mins < 2:
        return "under 2 minutes"
    if mins < 60:
        return f"about {mins} minute{'s' if mins != 1 else ''}"
    hrs = mins // 60
    rem = mins % 60
    if rem == 0:
        return f"about {hrs} hour{'s' if hrs != 1 else ''}"
    return f"about {hrs} hr {rem} min"


def format_distance(distance_m: float) -> str:
    """Human-readable distance string."""
    if distance_m < 1000:
        return f"{int(distance_m)} m"
    return f"{distance_m / 1000:.1f} km"


# ── Google Maps deep link ─────────────────────────────────────────────────────

def google_maps_directions_url(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str = "driving",
) -> str:
    """Return a Google Maps directions URL."""
    return (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}"
        f"&travelmode={mode}"
    )
