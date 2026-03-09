from __future__ import annotations
import requests

def fetch_arcgis_geojson(feature_server_url: str, bbox, out_sr: int = 4326) -> dict:
    minx, miny, maxx, maxy = bbox
    params = {
        "f": "geojson",
        "where": "1=1",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": out_sr,
        "outFields": "*",
        "returnGeometry": "true",
    }
    r = requests.get(f"{feature_server_url}/query", params=params, timeout=120)
    r.raise_for_status()
    return r.json()
