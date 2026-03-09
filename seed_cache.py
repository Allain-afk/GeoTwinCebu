#!/usr/bin/env python
"""
seed_cache.py — One-time script to pre-download Cebu City hazard layers
and upload them to Supabase Storage.

Run this ONCE on your local machine before deploying to Vercel:
  python seed_cache.py

Requirements:
  - .env file with SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET
  - Supabase Storage bucket already created (name matches SUPABASE_BUCKET)

The script downloads layers for the full Cebu City bounding box in tiles
(to avoid overwhelming the WFS/ArcGIS servers) and uploads each tile's
GeoJSON to Supabase. The Flask app will serve these cached files instantly.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# Add app/ to path so geo modules are importable
sys.path.insert(0, str(Path(__file__).parent / "app"))

from supabase import create_client
from shapely.geometry import box

# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BUCKET = os.environ.get("SUPABASE_BUCKET", "geojson-cache")

# Cebu City rough bounding box (minLon, minLat, maxLon, maxLat)
CEBU_CITY_BBOX = (123.80, 10.26, 123.95, 10.40)

# Tile grid — divide bbox into tiles to keep request sizes manageable
# 4x4 grid = 16 tiles covering Cebu City
TILE_COLS = 4
TILE_ROWS = 4

LAYERS_TO_SEED = ["lipad_flood_5yr", "lipad_flood_100yr", "mgb_landslide_susc"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_tiles(bbox, cols, rows):
    minlon, minlat, maxlon, maxlat = bbox
    dlon = (maxlon - minlon) / cols
    dlat = (maxlat - minlat) / rows
    tiles = []
    for r in range(rows):
        for c in range(cols):
            tile = (
                minlon + c * dlon,
                minlat + r * dlat,
                minlon + (c + 1) * dlon,
                minlat + (r + 1) * dlat,
            )
            tiles.append(tile)
    return tiles


def cache_key(layer_id, bbox):
    return f"{layer_id}_{bbox[0]:.4f}_{bbox[1]:.4f}_{bbox[2]:.4f}_{bbox[3]:.4f}.geojson"


def upload(client, key, data):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    client.storage.from_(BUCKET).upload(
        path=key,
        file=payload,
        file_options={"content-type": "application/json", "upsert": "true"},
    )


def already_exists(client, key):
    try:
        client.storage.from_(BUCKET).download(key)
        return True
    except Exception:
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    from geo.sources import fetch_layer_geojson

    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    tiles = make_tiles(CEBU_CITY_BBOX, TILE_COLS, TILE_ROWS)

    total = len(LAYERS_TO_SEED) * len(tiles)
    done = 0
    errors = 0

    print(f"\nSeeding {len(LAYERS_TO_SEED)} layers × {len(tiles)} tiles = {total} uploads")
    print(f"Bucket: {BUCKET}\n")

    for layer_id in LAYERS_TO_SEED:
        print(f"▶ Layer: {layer_id}")
        for i, tile_bbox in enumerate(tiles):
            key = cache_key(layer_id, tile_bbox)

            # Skip if already uploaded
            if already_exists(client, key):
                print(f"  [{i+1}/{len(tiles)}] SKIP (already in bucket): {key}")
                done += 1
                continue

            print(f"  [{i+1}/{len(tiles)}] Fetching: {key} ...", end=" ", flush=True)
            try:
                aoi = box(*tile_bbox)
                # Fetch directly — no local cache needed for seed script
                from geo.sources import LAYERS
                from geo.wfs import fetch_wfs_geojson
                from geo.arcgis import fetch_arcgis_geojson

                layer = LAYERS[layer_id]
                fetch = layer["fetch"]
                ftype = fetch["type"]

                if ftype == "wfs":
                    fc = fetch_wfs_geojson(fetch["url"], fetch["typeName"], tile_bbox, srs="EPSG:4326")
                elif ftype == "arcgis":
                    fc = fetch_arcgis_geojson(fetch["url"], bbox=tile_bbox)
                else:
                    print("SKIP (unknown type)")
                    continue

                feat_count = len(fc.get("features", []))
                upload(client, key, fc)
                print(f"✅ {feat_count} features uploaded")
                done += 1
            except Exception as e:
                print(f"❌ ERROR: {e}")
                errors += 1

            # Small delay to avoid hammering the source servers
            time.sleep(1.5)

        print()

    print(f"Done. {done}/{total} tiles seeded. {errors} errors.")
    if errors:
        print("Re-run the script to retry failed tiles (skips already-uploaded ones).")


if __name__ == "__main__":
    main()
