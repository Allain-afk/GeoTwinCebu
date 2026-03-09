from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

import requests

from .wfs import fetch_wfs_geojson
from .arcgis import fetch_arcgis_geojson

LIPAD_WFS = "https://lipad-fmc.dream.upd.edu.ph/geoserver/wfs"
MGB_LANDSLIDE_FS = (
    "https://controlmap.mgb.gov.ph/arcgis/rest/services/GeospatialDataInventory/"
    "GDI_Detailed_Landslide_and_Flood_Susceptibility_Map_Series1/FeatureServer/0"
)

LAYERS: Dict[str, Dict[str, Any]] = {
    "lipad_flood_5yr": {
        "title": "Flood Risk — 5-year",
        "kind": "vector",
        "source": "LiPAD FMC GeoServer WFS",
        "fetch": {"type": "wfs", "url": LIPAD_WFS, "typeName": "geonode:ph072217000_fh5yr_10m"},
        "style": {"color": "#2b83ba", "fillOpacity": 0.35, "weight": 1},
        "legend": "Areas prone to flooding in a 5-year rain event.",
    },
    "lipad_flood_100yr": {
        "title": "Flood Risk — 100-year",
        "kind": "vector",
        "source": "LiPAD FMC GeoServer WFS",
        "fetch": {"type": "wfs", "url": LIPAD_WFS, "typeName": "geonode:ph072217000_fh100yr_10m"},
        "style": {"color": "#1d4ed8", "fillOpacity": 0.28, "weight": 1},
        "legend": "Areas prone to flooding in an extreme 100-year rain event.",
    },
    "mgb_landslide_susc": {
        "title": "Landslide Risk",
        "kind": "vector",
        "source": "MGB ArcGIS FeatureServer",
        "fetch": {"type": "arcgis", "url": MGB_LANDSLIDE_FS},
        "style": {"color": "#b91c1c", "fillOpacity": 0.25, "weight": 1},
        "legend": "Areas susceptible to landslides (MGB data).",
        "attrs_hint": ["LandslideSus", "LS", "SUSCEPT", "CLASS", "LANDSLIDE"],
    },
}

BASEMAPS = [
    {
        "id": "osm",
        "name": "Street Map",
        "type": "xyz",
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; OpenStreetMap contributors",
    },
    {
        "id": "opentopo",
        "name": "Terrain Map",
        "type": "xyz",
        "url": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "attribution": "&copy; OpenTopoMap (CC-BY-SA)",
    },
]


# ── Cache key builder ─────────────────────────────────────────────────────────

def _cache_key(layer_id: str, bbox) -> str:
    return f"{layer_id}_{bbox[0]:.4f}_{bbox[1]:.4f}_{bbox[2]:.4f}_{bbox[3]:.4f}.geojson"


# ── Supabase Storage helpers ──────────────────────────────────────────────────

def _supabase_client():
    """Return a Supabase client if credentials are configured, else None."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None, None
    try:
        from supabase import create_client
        bucket = os.environ.get("SUPABASE_BUCKET", "geojson-cache")
        return create_client(url, key), bucket
    except Exception:
        return None, None


def _supabase_read(key: str) -> Optional[dict]:
    """Try to read a cached GeoJSON from Supabase Storage. Returns None on miss/error."""
    client, bucket = _supabase_client()
    if client is None:
        return None
    try:
        response = client.storage.from_(bucket).download(key)
        return json.loads(response.decode("utf-8"))
    except Exception:
        return None


def _supabase_write(key: str, data: dict) -> None:
    """Upload a GeoJSON dict to Supabase Storage. Silently ignores errors."""
    client, bucket = _supabase_client()
    if client is None:
        return
    try:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        # upsert=True overwrites if key already exists
        client.storage.from_(bucket).upload(
            path=key,
            file=payload,
            file_options={"content-type": "application/json", "upsert": "true"},
        )
    except Exception:
        pass


# ── Local disk cache (used when running locally without Supabase) ─────────────

def _local_read(cache_dir: Optional[Path], key: str) -> Optional[dict]:
    if cache_dir is None:
        return None
    path = cache_dir / key
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _local_write(cache_dir: Optional[Path], key: str, data: dict) -> None:
    if cache_dir is None:
        return
    try:
        cache_dir.mkdir(exist_ok=True, parents=True)
        (cache_dir / key).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── Public helpers ────────────────────────────────────────────────────────────

def clear_cache_if_requested(cache_dir: Optional[Path], options: Dict[str, Any]) -> None:
    """Clear local disk cache only (Supabase cache is not wiped to avoid accidental data loss)."""
    if options.get("cache_refresh") and cache_dir:
        for p in cache_dir.glob("*.geojson"):
            try:
                p.unlink()
            except Exception:
                pass


def fetch_layer_geojson(
    layer_id: str,
    cache_dir: Optional[Path],
    aoi,
) -> Optional[dict]:
    """
    Fetch a GeoJSON layer for the given AOI, with a two-tier cache:
      1. Supabase Storage (works on Vercel)
      2. Local disk cache (works when running locally without Supabase)
    Falls back to live fetch from LiPAD / MGB if cache misses.
    """
    layer = LAYERS.get(layer_id)
    if not layer:
        return None

    bbox = aoi.bounds
    key = _cache_key(layer_id, bbox)

    # 1. Try Supabase cache
    cached = _supabase_read(key)
    if cached is not None:
        return cached

    # 2. Try local disk cache
    cached = _local_read(cache_dir, key)
    if cached is not None:
        return cached

    # 3. Live fetch
    fetch = layer.get("fetch", {})
    ftype = fetch.get("type")
    try:
        if ftype == "wfs":
            fc = fetch_wfs_geojson(fetch["url"], fetch["typeName"], bbox, srs="EPSG:4326")
        elif ftype == "arcgis":
            fc = fetch_arcgis_geojson(fetch["url"], bbox=bbox)
        else:
            return None
    except Exception:
        return None

    # 4. Write to both caches
    _supabase_write(key, fc)
    _local_write(cache_dir, key, fc)

    return fc
