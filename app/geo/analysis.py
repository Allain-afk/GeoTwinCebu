from __future__ import annotations

from typing import Optional

from shapely.geometry import shape
from shapely.ops import unary_union

WGS84 = "EPSG:4326"


def check_hazard_at_point(lat: float, lon: float, layers_cache: dict) -> list[str]:
    """
    Check if a WGS84 point overlaps any loaded hazard layers.
    layers_cache: dict of layer_id -> GeoJSON FeatureCollection
    Returns a list of plain-language warning strings.
    """
    from shapely.geometry import Point
    pt = Point(lon, lat)
    warnings = []

    flood_ids = [lid for lid in layers_cache if "flood" in lid]
    landslide_ids = [lid for lid in layers_cache if "landslide" in lid or "susc" in lid]

    for lid in flood_ids:
        fc = layers_cache[lid]
        union = _union_fc(fc)
        if union and pt.within(union):
            warnings.append("⚠️ This location is in a flood-prone area. Move to higher ground immediately.")
            break  # one flood warning is enough

    for lid in landslide_ids:
        fc = layers_cache[lid]
        union = _union_fc(fc)
        if union and pt.within(union):
            warnings.append("⚠️ This location is in a landslide-susceptible area. Avoid steep slopes and stay on main roads.")
            break

    return warnings


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
