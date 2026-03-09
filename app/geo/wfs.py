from __future__ import annotations
from typing import Tuple
import requests

def fetch_wfs_geojson(wfs_url: str, type_name: str, bbox: Tuple[float,float,float,float], srs: str="EPSG:4326") -> dict:
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "srsName": srs,
        "bbox": f"{minx},{miny},{maxx},{maxy},{srs}",
    }
    r = requests.get(wfs_url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()
