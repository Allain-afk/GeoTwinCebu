"""
AOI-based analysis: area stats and plain-language interpretation for GeoTwin report.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from shapely.geometry import shape
from shapely.ops import unary_union, transform
from pyproj import Transformer

from .boundary import parse_aoi, WGS84
from .sources import LAYERS, fetch_layer_geojson

PRS92_ZONE4 = "EPSG:3124"


def _union_fc(fc: dict):
    geoms = []
    for f in fc.get("features", []):
        try:
            geoms.append(shape(f.get("geometry")))
        except Exception:
            pass
    if not geoms:
        return None
    return unary_union(geoms)


def run_aoi_analysis(
    aoi_payload: Dict[str, Any],
    active_layer_ids: List[str],
    cache_dir,
) -> Dict[str, Any]:
    """
    Run AOI-based analysis: fetch layers, compute overlaps, generate interpretation.

    aoi_payload: { bbox | circle | geometry } — same format as /api/analyze
    active_layer_ids: list of layer IDs from LAYERS
    cache_dir: Path for layer cache

    Returns: { aoi_geom, area_m2, layers, stats, interpretation, layer_summaries }
    """
    aoi_geom = parse_aoi(aoi_payload)
    if aoi_geom is None:
        return {"error": "Could not parse AOI. Use bbox, circle, or geometry."}

    # AOI area in m² (use projected CRS for accurate area)
    fwd = Transformer.from_crs(WGS84, PRS92_ZONE4, always_xy=True)
    aoi_proj = transform(lambda x, y, z=None: fwd.transform(x, y), aoi_geom)
    area_m2 = aoi_proj.area

    layer_summaries = []
    stats = {"aoi_area_ha": round(area_m2 / 10000, 4), "aoi_area_m2": round(area_m2, 2)}

    # Filter to valid layer IDs
    valid_ids = [lid for lid in active_layer_ids if lid in LAYERS]

    interpretation_parts = []
    hazard_found = []

    for lid in valid_ids:
        fc = fetch_layer_geojson(layer_id=lid, cache_dir=cache_dir, aoi=aoi_geom)
        layer_info = LAYERS[lid]
        title = layer_info.get("title", lid)
        legend = layer_info.get("legend", "")

        if not fc or not fc.get("features"):
            layer_summaries.append({
                "layer_id": lid,
                "title": title,
                "legend": legend,
                "overlap_ha": 0,
                "overlap_pct": 0,
                "feature_count": 0,
            })
            continue

        union = _union_fc(fc)
        if union is None:
            layer_summaries.append({
                "layer_id": lid,
                "title": title,
                "legend": legend,
                "overlap_ha": 0,
                "overlap_pct": 0,
                "feature_count": len(fc.get("features", [])),
            })
            continue

        try:
            overlap = aoi_geom.intersection(union)
        except Exception:
            overlap = None
        if overlap is None or overlap.is_empty:
            overlap_ha = 0
            overlap_pct = 0
        else:
            overlap_proj = transform(lambda x, y, z=None: fwd.transform(x, y), overlap)
            overlap_m2 = overlap_proj.area
            overlap_ha = overlap_m2 / 10000
            overlap_pct = (overlap_m2 / area_m2 * 100) if area_m2 > 0 else 0

        layer_summaries.append({
            "layer_id": lid,
            "title": title,
            "legend": legend,
            "overlap_ha": round(overlap_ha, 4),
            "overlap_pct": round(overlap_pct, 2),
            "feature_count": len(fc.get("features", [])),
        })

        if overlap_pct > 0:
            if "flood" in lid:
                interpretation_parts.append(
                    f"Flood-prone area (5- or 100-year): {overlap_pct:.1f}% of AOI overlaps."
                )
            elif "landslide" in lid or "susc" in lid:
                interpretation_parts.append(
                    f"Landslide-susceptible area: {overlap_pct:.1f}% of AOI overlaps."
                )
            else:
                interpretation_parts.append(
                    f"{title}: {overlap_pct:.1f}% of AOI overlaps."
                )

    if not interpretation_parts:
        interpretation = "No hazard zones overlap the defined AOI based on active layers."
    else:
        interpretation = " ".join(interpretation_parts)

    return {
        "area_m2": area_m2,
        "stats": stats,
        "layer_summaries": layer_summaries,
        "interpretation": interpretation,
    }
