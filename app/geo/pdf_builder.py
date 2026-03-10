"""
PDF report generation for GeoTwin analysis results.
"""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def build_report_pdf(
    stats: Dict[str, Any],
    interpretation: str,
    layer_summaries: List[Dict[str, Any]],
    route_data: Optional[Dict[str, Any]] = None,
    map_image: Optional[bytes] = None,
) -> bytes:
    """
    Build a PDF report from analysis results. Returns PDF as bytes.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        "CustomH2",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=8,
        spaceBefore=16,
    )
    body_style = styles["Normal"]

    story = []

    # Title
    story.append(Paragraph("GeoTwin Cebu — Analysis Report", title_style))
    story.append(Spacer(1, 0.5 * cm))

    # Map image (if provided) — constrain to fit frame and avoid "Flowable too large" error
    if map_image:
        try:
            if isinstance(map_image, str):
                img_bytes = base64.b64decode(map_image)
            else:
                img_bytes = map_image
            img_io = BytesIO(img_bytes)
            page_width, page_height = A4[0], A4[1]
            frame_width = page_width - 4 * cm
            frame_height = page_height - 4 * cm
            img = Image(img_io, width=frame_width, height=frame_height, kind="proportional")
            story.append(img)
            story.append(Spacer(1, 0.5 * cm))
        except Exception:
            pass  # Skip image on decode error

    # Route Information (if provided)
    if route_data:
        story.append(Paragraph("Route Information", h2_style))
        route_rows = []

        origin = route_data.get("origin")
        if origin:
            route_rows.append(["Pinned Location (Origin)", ""])
            o_lat, o_lon = origin.get("lat"), origin.get("lon")
            wgs84_orig = f"{o_lat:.6f}°, {o_lon:.6f}°" if o_lat is not None and o_lon is not None else "N/A"
            route_rows.append(["  WGS84 (Lat, Lon)", wgs84_orig])
            prs92 = origin.get("prs92", {})
            route_rows.append(["  PRS92 (Northing, Easting)", f"N: {prs92.get('northing', 'N/A')}, E: {prs92.get('easting', 'N/A')}"])
            route_rows.append(["", ""])

        dest = route_data.get("destination")
        if dest:
            route_rows.append(["Evacuation Area (Destination)", ""])
            route_rows.append(["  Name", dest.get("name", "N/A")])
            d_lat, d_lon = dest.get("lat"), dest.get("lon")
            wgs84_dest = f"{d_lat:.6f}°, {d_lon:.6f}°" if d_lat is not None and d_lon is not None else "N/A"
            route_rows.append(["  WGS84 (Lat, Lon)", wgs84_dest])
            prs92 = dest.get("prs92", {})
            route_rows.append(["  PRS92 (Northing, Easting)", f"N: {prs92.get('northing', 'N/A')}, E: {prs92.get('easting', 'N/A')}"])
            elev = dest.get("elevation", {})
            route_rows.append(["  Ellipsoidal Height", elev.get("ellipsoidal", "N/A")])
            route_rows.append(["  Orthometric Height", elev.get("orthometric", "N/A")])
            route_rows.append(["", ""])

        trip = route_data.get("trip")
        if trip:
            route_rows.append(["Trip Stats", ""])
            route_rows.append(["  Travel Time", trip.get("duration_text", "N/A")])
            route_rows.append(["  Distance", trip.get("distance_text", "N/A")])

        if route_rows:
            route_table = Table(route_rows, colWidths=[6 * cm, 8 * cm])
            route_table.setStyle(
                TableStyle([
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ])
            )
            story.append(route_table)
            story.append(Spacer(1, 0.5 * cm))

    # AOI Stats
    story.append(Paragraph("Area of Interest", h2_style))
    aoi_area_ha = stats.get("aoi_area_ha", 0)
    aoi_area_m2 = stats.get("aoi_area_m2", 0)
    story.append(
        Paragraph(
            f"AOI area: <b>{aoi_area_ha:.4f}</b> ha "
            f"({aoi_area_m2:,.0f} m²)",
            body_style,
        )
    )
    story.append(Spacer(1, 0.3 * cm))

    # Interpretation
    story.append(Paragraph("Interpretation", h2_style))
    story.append(Paragraph(interpretation, body_style))
    story.append(Spacer(1, 0.5 * cm))

    # Layer summaries table
    story.append(Paragraph("Layer Overlays", h2_style))
    if layer_summaries:
        table_data = [["Layer", "Overlap (ha)", "Overlap (%)", "Features"]]
        for ls in layer_summaries:
            table_data.append([
                ls.get("title", ls.get("layer_id", "")),
                str(ls.get("overlap_ha", 0)),
                str(ls.get("overlap_pct", 0)) + "%",
                str(ls.get("feature_count", 0)),
            ])
        t = Table(table_data, colWidths=[8 * cm, 3 * cm, 3 * cm, 2.5 * cm])
        t.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ])
        )
        story.append(t)
        story.append(Spacer(1, 0.5 * cm))

        # Legends
        story.append(Paragraph("Legend", h2_style))
        for ls in layer_summaries:
            title = ls.get("title", ls.get("layer_id", ""))
            legend = ls.get("legend", "")
            if legend:
                story.append(
                    Paragraph(f"<b>{title}</b>: {legend}", body_style)
                )
                story.append(Spacer(1, 0.2 * cm))
    else:
        story.append(Paragraph("No layers analyzed.", body_style))

    # Footer note
    story.append(Spacer(1, 1 * cm))
    story.append(
        Paragraph(
            "<i>Report generated by GeoTwin Cebu. "
            "Data: LiPAD FMC, MGB, OpenStreetMap. "
            "For planning and communication purposes.</i>",
            ParagraphStyle("Footer", parent=body_style, fontSize=8, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buf.getvalue()
