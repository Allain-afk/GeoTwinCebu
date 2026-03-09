from __future__ import annotations

import math
import re
from typing import Tuple

import pandas as pd
from shapely.geometry import Polygon, mapping, shape, Point
from shapely.ops import transform
from pyproj import Transformer

WGS84 = "EPSG:4326"
PRS92_ZONE4 = "EPSG:3124"

def parse_aoi(aoi_obj):
    if not aoi_obj:
        return None
    if isinstance(aoi_obj, dict) and aoi_obj.get("type") == "circle":
        center = aoi_obj.get("center")
        r_m = float(aoi_obj.get("radius_m", 1000))
        if not center or len(center) != 2:
            return None
        lat, lon = float(center[0]), float(center[1])
        return circle_buffer_wgs84(lon, lat, r_m)
    if isinstance(aoi_obj, dict) and aoi_obj.get("type") == "Feature":
        return shape(aoi_obj.get("geometry"))
    if isinstance(aoi_obj, dict) and aoi_obj.get("type") in ("Polygon","MultiPolygon"):
        return shape(aoi_obj)
    return None

def circle_buffer_wgs84(lon: float, lat: float, radius_m: float):
    fwd = Transformer.from_crs(WGS84, PRS92_ZONE4, always_xy=True)
    inv = Transformer.from_crs(PRS92_ZONE4, WGS84, always_xy=True)
    x, y = fwd.transform(lon, lat)
    poly_m = Point(x, y).buffer(radius_m)
    return transform(lambda x, y, z=None: inv.transform(x, y), poly_m)

def parse_manual_vertices_text(text: str, crs: str=WGS84) -> Tuple[dict, dict]:
    pts = []
    warnings = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[,\s]+", line)
        if len(parts) < 2:
            continue
        a = float(parts[0]); b = float(parts[1])
        if abs(a) > 50 and abs(b) < 50:
            lon, lat = a, b
        else:
            lat, lon = a, b
        pts.append((lon, lat))
    if len(pts) < 3:
        return None, {"warnings":["Need at least 3 points."]}
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    poly = Polygon(pts)
    if not poly.is_valid:
        warnings.append("Polygon is not valid (self-intersection). Check point order.")
    geom = poly
    if crs != WGS84:
        geom = _to_wgs84(poly, crs)
    qa = _basic_qa(geom, warnings=warnings)
    return mapping(geom), qa

def parse_coords_csv_text(text: str, crs: str=WGS84) -> Tuple[dict, dict]:
    from io import StringIO
    df = pd.read_csv(StringIO(text))
    lower = {c.lower(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n in lower:
                return lower[n]
        return None
    x_c = pick("e","easting","x","lon","longitude")
    y_c = pick("n","northing","y","lat","latitude")
    if not x_c or not y_c:
        return None, {"warnings":["Could not detect coordinate columns. Use headers like E,N or X,Y or lon,lat."]}
    pts = list(zip(df[x_c].astype(float).tolist(), df[y_c].astype(float).tolist()))
    if len(pts) < 3:
        return None, {"warnings":["Need at least 3 points."]}
    poly = Polygon(pts + [pts[0]])
    warnings = []
    if not poly.is_valid:
        warnings.append("Polygon is not valid (self-intersection). Check point order.")
    geom = poly
    if crs != WGS84:
        geom = _to_wgs84(poly, crs)
    qa = _basic_qa(geom, warnings=warnings)
    return mapping(geom), qa

def parse_traverse_text(text: str, crs: str=WGS84) -> Tuple[dict, dict]:
    warnings = [
        "Traverse parsing is approximate. For legal surveys, compute with certified software/standards.",
        "Provide START: lat,lon on the first line for best results."
    ]
    start = None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for l in lines[:3]:
        m = re.search(r"start\s*:\s*([-\d\.]+)\s*[, ]\s*([-\d\.]+)", l, flags=re.IGNORECASE)
        if m:
            lat = float(m.group(1)); lon = float(m.group(2))
            start = (lon, lat)
            break
    if start is None:
        return None, {"warnings": ["Missing START: lat,lon line. Example: START: 10.3157,123.8854"]}
    fwd = Transformer.from_crs(WGS84, PRS92_ZONE4, always_xy=True)
    inv = Transformer.from_crs(PRS92_ZONE4, WGS84, always_xy=True)
    x, y = fwd.transform(start[0], start[1])
    pts_m = [(x, y)]
    for l in lines:
        if re.search(r"start\s*:", l, flags=re.IGNORECASE):
            continue
        dm = re.findall(r"[-+]?\d+(\.\d+)?", l)
        if not dm:
            continue
        dist = float(dm[-1])
        az = _bearing_to_azimuth_deg(l)
        if az is None:
            continue
        rad = math.radians(az)
        dx = dist * math.sin(rad)
        dy = dist * math.cos(rad)
        x += dx; y += dy
        pts_m.append((x, y))
    if len(pts_m) < 4:
        return None, {"warnings":["Not enough courses parsed. Check bearing formats."]}
    pts_m.append(pts_m[0])
    pts_ll = [inv.transform(px, py) for px, py in pts_m]
    poly = Polygon(pts_ll)
    if not poly.is_valid:
        warnings.append("Polygon is not valid (self-intersection).")
    qa = _basic_qa(poly, warnings=warnings)
    qa["closure_note"] = "Closure is not computed rigorously in this prototype."
    return mapping(poly), qa

def _bearing_to_azimuth_deg(text: str):
    t = text.upper()
    m = re.search(r"\b([NS])\s*([0-9]{1,3})\D+([0-9]{1,2})?\D*([0-9]{1,2})?\s*([EW])\b", t)
    if m:
        ns = m.group(1)
        deg = float(m.group(2))
        minute = float(m.group(3) or 0)
        sec = float(m.group(4) or 0)
        ew = m.group(5)
        theta = deg + minute/60.0 + sec/3600.0
        if ns == "N" and ew == "E": return theta
        if ns == "N" and ew == "W": return 360 - theta
        if ns == "S" and ew == "E": return 180 - theta
        if ns == "S" and ew == "W": return 180 + theta
    m2 = re.search(r"\b([NS])\s*([0-9]{1,3}(\.\d+)?)\s*([EW])\b", t)
    if m2:
        ns, deg_s, _, ew = m2.groups()
        theta = float(deg_s)
        if ns == "N" and ew == "E": return theta
        if ns == "N" and ew == "W": return 360 - theta
        if ns == "S" and ew == "E": return 180 - theta
        if ns == "S" and ew == "W": return 180 + theta
    return None

def _to_wgs84(geom, crs: str):
    tr = Transformer.from_crs(crs, WGS84, always_xy=True)
    return transform(lambda x, y, z=None: tr.transform(x, y), geom)

def _basic_qa(poly, warnings=None):
    warnings = list(warnings or [])
    fwd = Transformer.from_crs(WGS84, PRS92_ZONE4, always_xy=True)
    poly_m = transform(lambda x, y, z=None: fwd.transform(x, y), poly)
    area_m2 = poly_m.area
    perim_m = poly_m.length
    if area_m2 <= 0:
        warnings.append("Area computed as 0 or negative. Check geometry.")
    return {"area_m2": round(area_m2, 3), "perimeter_m": round(perim_m, 3), "warnings": warnings}
