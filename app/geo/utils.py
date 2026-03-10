"""Geodetic utilities: coordinate conversion (WGS84 → PRS92) and elevation lookup."""
from __future__ import annotations

from pyproj import Transformer

WGS84 = "EPSG:4326"
PRS92_ZONE4 = "EPSG:3124"

_transformer = None


def _get_transformer():
    global _transformer
    if _transformer is None:
        _transformer = Transformer.from_crs(WGS84, PRS92_ZONE4, always_xy=True)
    return _transformer


def convert_wgs84_to_prs92(lat: float, lon: float) -> dict[str, str]:
    """
    Convert WGS84 (lat, lon) to PRS92 Zone 4 (Northing, Easting).
    Returns dict with keys 'northing' and 'easting', values formatted to 2 decimal places.
    """
    t = _get_transformer()
    easting, northing = t.transform(lon, lat)
    return {
        "northing": f"{northing:.2f}",
        "easting": f"{easting:.2f}",
    }


def get_elevation_data(lat: float, lon: float, timeout: int = 5) -> dict[str, str]:
    """
    Fetch elevation at (lat, lon).
    Open-Elevation returns orthometric (MSL) height.
    Ellipsoidal height requires a geoid model (not available without local DEM), so N/A.
    Returns {"ellipsoidal": "N/A"|str, "orthometric": "N/A"|str}.
    """
    result = {"ellipsoidal": "N/A", "orthometric": "N/A"}
    try:
        import requests

        url = "https://api.open-elevation.com/api/v1/lookup"
        payload = {"locations": [{"latitude": lat, "longitude": lon}]}
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            results = data.get("results", [])
            if results:
                elev = results[0].get("elevation")
                if elev is not None:
                    result["orthometric"] = f"{elev:.2f}"
    except Exception:
        pass
    return result
