"""One-page PDF situation brief + map preview figure."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .roads import BLOCKED, CLEAR, NODATA, UNCERTAIN

STATUS_RGB = {BLOCKED: "#e00000", UNCERTAIN: "#ff9900", CLEAR: "#10b010", NODATA: "#888888"}


def make_figure(path, ortho_rgb, valid, mask, scored, grid):
    h, w = grid.shape
    l, t = grid.transform * (0, 0)
    r, b = grid.transform * (w, h)
    img = np.clip(ortho_rgb, 0, 255).astype(np.uint8).copy()
    img[~valid] = 255
    fig, ax = plt.subplots(figsize=(8, 8), dpi=130)
    ax.imshow(img, extent=(l, r, b, t))
    ov = np.zeros((h, w, 4), np.float32)
    ov[mask] = (1, 0.1, 0.1, 0.35)
    ax.imshow(ov, extent=(l, r, b, t))
    for st in (CLEAR, NODATA, UNCERTAIN, BLOCKED):
        sub = scored[scored.status == st]
        for g in sub.geometry:
            xs, ys = g.xy
            ax.plot(xs, ys, color=STATUS_RGB[st], lw=4.5 if st == BLOCKED else 2.2, solid_capstyle="butt")
    ax.set_xlim(l, r)
    ax.set_ylim(b, t)
    ax.set_xlabel(f"Easting (m), {grid.crs.to_string()}")
    ax.set_ylabel("Northing (m)")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=6)
    # scale bar + north arrow
    bar = 200 if (r - l) > 800 else 100
    x0, y0 = l + (r - l) * 0.04, b + (t - b) * 0.05
    ax.plot([x0, x0 + bar], [y0, y0], color="k", lw=4)
    ax.text(x0 + bar / 2, y0 + (t - b) * 0.012, f"{bar} m", ha="center", fontsize=8, weight="bold",
            bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))
    ax.annotate("N", xy=(r - (r - l) * 0.05, b + (t - b) * 0.14), xytext=(r - (r - l) * 0.05, b + (t - b) * 0.06),
                ha="center", fontsize=11, weight="bold", arrowprops=dict(arrowstyle="-|>", lw=2),
                bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    ax.legend(handles=[Line2D([0], [0], color=STATUS_RGB[BLOCKED], lw=4, label="Road BLOCKED"),
                       Line2D([0], [0], color=STATUS_RGB[UNCERTAIN], lw=3, label="Road UNCERTAIN"),
                       Line2D([0], [0], color=STATUS_RGB[CLEAR], lw=3, label="Road CLEAR"),
                       Patch(fc=(1, 0.1, 0.1, 0.35), label="Detected change")],
              loc="upper right", fontsize=7, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def make_pdf(path, rep, blocked, img_path):
    ss = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=ss["Title"], fontSize=17, spaceAfter=2, alignment=0)
    B = ParagraphStyle("B", parent=ss["BodyText"], fontSize=8.8, leading=11.2, spaceAfter=1.5)
    S = ParagraphStyle("S", parent=B, fontSize=7, leading=8.5, textColor=colors.HexColor("#444444"))
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=10 * mm, bottomMargin=8 * mm, title="MAPPA situation brief")
    geo, ch, rd = rep["georeferencing"], rep["change"], rep["roads"]
    L = rd["length_m_by_status"]
    el = [Paragraph("MAPPA: rapid post-landslide map brief", H)]
    if rep["simulated_data"]:
        t = Table([[Paragraph("<b>SIMULATED DEMONSTRATION DATA.</b> Imagery, roads and the landslide are synthetic. "
                              "Not for operational use.", B)]], colWidths=[186 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffe9a8")),
                               ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#b07800"))]))
        el += [t, Spacer(1, 2 * mm)]
    el.append(Image(str(img_path), width=124 * mm, height=124 * mm))
    el[-1].hAlign = "LEFT"
    el.append(Spacer(1, 1.5 * mm))
    summ = [["Area mapped", f"{rep['area_km2']} km2 at {rep['analysis_grid_m']:g} m/px"],
            ["Changed area", f"{ch['changed_area_m2']:,} m2 in {ch['n_change_polygons']} patches"],
            ["Roads blocked", f"{L.get('BLOCKED', 0):.0f} m"],
            ["Roads uncertain", f"{L.get('UNCERTAIN', 0):.0f} m"],
            ["Roads clear", f"{L.get('CLEAR', 0):.0f} m"]]
    t1 = Table(summ, colWidths=[26 * mm, 32 * mm])
    t1.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#ffd0d0"))]))
    rows = [["Blocked stretch (road)", "Length m", "Changed"]]
    rows += [[b["road"][:18], f"{b['length_m']:.0f}", f"{b['mean_changed_frac']:.0%}"] for b in blocked[:8]] \
        or [["none detected", "", ""]]
    t2 = Table(rows, colWidths=[30 * mm, 14 * mm, 14 * mm])
    t2.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd"))]))
    side = Table([[t1], [Spacer(1, 3 * mm)], [t2]])
    top = Table([[el[-2], side]], colWidths=[128 * mm, 58 * mm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    el = el[:-2] + [top, Spacer(1, 2 * mm)]

    el.append(Paragraph("<b>Accuracy statement.</b> " + geo["statement"] +
                        f" Method: {geo['method']} ({geo['n_inliers']} inliers, registration RMS "
                        f"{geo['registration_rms_m']} m). GPS-only georeference was off by about "
                        f"{geo['gps_only_correction_m']} m before correction. Absolute accuracy is limited by the base layer "
                        f"(assumed +/-{geo['base_layer_abs_accuracy_95_m_assumed']:g} m, 95%).", B))
    if "validation" in rep:
        v = rep["validation"]
        el.append(Paragraph(f"<b>Synthetic validation (known truth).</b> Injected GPS-only error averaged {v['error_before_mean_m']} m "
                            f"(max {v['error_before_max_m']} m). After registration the mean error is {v['error_after_mean_m']} m "
                            f"(max {v['error_after_max_m']} m) over {v['n_points']} check points. "
                            f"Road check vs. true slide footprint: precision {v['roads_vs_truth']['precision']}, recall {v['roads_vs_truth']['recall']}. "
                            f"This is a synthetic test, not a field accuracy claim.", B))
    el.append(Paragraph("<b>Change detection limits.</b> " + ch["caveat"] +
                        (f" Height check used (DSM minus DEM, {ch['vertical_bias_removed_m']} m vertical bias removed)."
                         if ch["height_used"] else " No height data used."), B))
    th = rd["thresholds"]
    el.append(Paragraph(f"<b>Road rule.</b> {th['seg_len_m']:g} m segments, {th['buffer_m']:g} m buffer. "
                        f"BLOCKED: changed share &gt;= {th['blocked_frac']:.0%} and height anomaly &gt;= {th['blocked_height_m']} m "
                        f"(without height data: &gt;= {th['blocked_frac_no_dsm']:.0%}). UNCERTAIN: changed share &gt;= "
                        f"{th['uncertain_frac']:.0%}. Thresholds are tunable and not field-calibrated.", B))
    el.append(Paragraph("<b>Processing.</b> " + rep.get("processing_time_statement", ""), B))
    el.append(Paragraph("<b>Provenance.</b> " + (rep["provenance"] or "n/a") +
                        " Built entirely with open-source tools (OpenDroneMap, OpenCV, rasterio, GeoPandas, "
                        "Shapely, Matplotlib, ReportLab). Fully offline. Open GeoPackage / GeoJSON / KML / GeoTIFF in QGIS.", S))
    doc.build(el)
