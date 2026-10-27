"""End-to-end offline pipeline: ortho (+DSM) + base imagery (+DEM) + roads -> georeferenced change map."""
from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path

import cv2
import numpy as np

from . import __version__, brief, change, export, georef, grid as G, roads as R


class Timer:
    def __init__(self):
        self.t = {}
        self._t0 = time.perf_counter()

    def lap(self, name, since):
        self.t[name] = round(time.perf_counter() - since, 2)

    def total(self):
        return round(time.perf_counter() - self._t0, 2)


def hardware() -> dict:
    ram = None
    try:
        ram = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30, 1)
    except (ValueError, OSError, AttributeError):
        pass
    return {"cpu_count": os.cpu_count(), "ram_gb": ram, "platform": platform.platform(), "gpu_used": False}


def run(ortho: str, base: str, roads_path: str, out: str, dsm: str | None = None, dem: str | None = None,
        grid_res: float = 1.0, base_acc95: float = 10.0, simulated: bool = False,
        provenance: str = "", thresholds: dict | None = None, truth: str | None = None) -> dict:
    thresholds = thresholds or {}
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    T = Timer()

    s = time.perf_counter()
    grid = G.make_grid(ortho, grid_res)
    o_rgb, o_valid = G.read_rgb(ortho, grid)
    b_rgb, b_valid = G.read_rgb(base, grid)
    base_res = G.native_res_m(base)
    T.lap("1_load_and_resample", s)

    s = time.perf_counter()
    blur = max(0.0, base_res / grid_res / 2.0)
    M, reg = georef.register(o_rgb, o_valid, b_rgb, b_valid, grid_res, blur_px=blur)
    gps_err = georef.shift_m(M, grid.shape, grid_res)
    acc95 = georef.accuracy95(reg, base_acc95, grid_res)
    T.lap("2_register_to_base", s)

    s = time.perf_counter()
    size = (grid.width, grid.height)
    o_al = cv2.warpAffine(o_rgb, M, size, flags=cv2.INTER_LINEAR, borderValue=0)
    v_al = cv2.warpAffine(o_valid.astype(np.uint8), M, size, flags=cv2.INTER_NEAREST).astype(bool) & b_valid
    colour_mask, diff, cinfo = change.colour_change(o_al, b_rgb, v_al, grid_res, base_res,
                                                     min_area_m2=thresholds.get("min_area_m2", 150.0))
    anomaly, bias, hmask = None, None, None
    if dsm and dem:
        dsm_g = cv2.warpAffine(G.read_band(dsm, grid), M, size, flags=cv2.INTER_LINEAR, borderValue=np.nan)
        dem_g = G.read_band(dem, grid)
        anomaly, bias = change.height_anomaly(dsm_g, dem_g, colour_mask, v_al)
    mask, hmask = change.combine(colour_mask, anomaly, v_al, grid_res,
                                 height_change_m=thresholds.get("height_change_m", 1.0))
    T.lap("3_change_detection", s)

    s = time.perf_counter()
    road_kw = {k: v for k, v in thresholds.items() if k in R.DEFAULTS}
    p = {**R.DEFAULTS, **road_kw}
    roads_gdf = R.load_roads(roads_path, grid.crs)
    segs = R.segments(roads_gdf, p["seg_len_m"])
    scored = R.score(segs, mask, anomaly, v_al, grid, **road_kw)
    blocked = R.stretches(scored, R.BLOCKED)
    uncertain = R.stretches(scored, R.UNCERTAIN)
    T.lap("4_road_scoring", s)

    s = time.perf_counter()
    export.write_corrected_ortho(ortho, str(out_dir / "orthophoto_georef.tif"), M, grid.transform)
    export.write_raster(out_dir / "change_mask.tif", mask.astype(np.uint8), grid, "uint8", nodata=255)
    if anomaly is not None:
        export.write_raster(out_dir / "height_anomaly_m.tif", np.nan_to_num(anomaly, nan=-9999), grid,
                            "float32", nodata=-9999)
    changes = export.mask_to_polygons(mask, grid, min_area_m2=thresholds.get("min_area_m2", 150.0))
    export.write_vector(changes, out_dir / "change_polygons", "change_polygons")
    export.write_vector(scored, out_dir / "roads_status", "roads_status")
    note = (f"MAPPA {__version__}. Positional accuracy +/-{acc95:.0f} m (95%), unverified against ground truth. "
            + ("SIMULATED DEMO DATA. " if simulated else ""))
    export.write_roads_kml(scored, str(out_dir / "roads_status.kml"), "Road status", note)
    export.write_changes_kml(changes, str(out_dir / "change_polygons.kml"), "Changes")
    T.lap("5_export_geodata", s)

    valid_km2 = float(v_al.sum() * grid_res ** 2 / 1e6)
    status_len = scored.groupby("status").length_m.sum().round(0).to_dict()
    report = {
        "tool": f"mappa {__version__}",
        "simulated_data": simulated,
        "provenance": provenance,
        "inputs": {"ortho": os.path.basename(ortho), "base": os.path.basename(base), "roads": os.path.basename(roads_path),
                   "dsm": os.path.basename(dsm) if dsm else None, "dem": os.path.basename(dem) if dem else None},
        "analysis_grid_m": grid_res,
        "area_km2": round(valid_km2, 3),
        "georeferencing": {
            "method": reg.get("method"), "gps_only_correction_m": round(gps_err, 2),
            "registration_rms_m": None if reg.get("rms_m") != reg.get("rms_m") else round(reg.get("rms_m", float("nan")), 2),
            "n_inliers": reg.get("n_inliers"), "n_matches": reg.get("n_matches"),
            "scale": reg.get("scale"), "rotation_deg": reg.get("rotation_deg"),
            "base_layer_abs_accuracy_95_m_assumed": base_acc95,
            "horizontal_accuracy_95_m": round(acc95, 1),
            "statement": f"Positional accuracy +/-{acc95:.0f} m (95%), unverified against ground truth. "
                         f"Relative accuracy inside the map is much better (centimetre-to-decimetre class) "
                         f"but was not measured here.",
        },
        "change": {**{k: (round(v, 2) if isinstance(v, float) else v) for k, v in cinfo.items()},
                   "changed_area_m2": int(mask.sum() * grid_res ** 2), "n_change_polygons": int(len(changes)),
                   "height_used": anomaly is not None,
                   "vertical_bias_removed_m": None if bias is None else round(bias, 2),
                   "base_native_resolution_m": round(base_res, 1),
                   "caveat": f"Detection is coarse: limited by the {base_res:.0f} m base imagery; small debris is not resolved."},
        "roads": {"thresholds": p, "segments": int(len(scored)), "length_m_by_status": status_len,
                  "blocked_stretches": [{k: v for k, v in b.items() if not k.startswith("_")} for b in blocked],
                  "uncertain_stretches": [{k: v for k, v in b.items() if not k.startswith("_")} for b in uncertain]},
        "hardware": hardware(),
    }

    if truth:
        from . import demo_data
        report["validation"] = {"note": "SYNTHETIC scene with known injected GPS error; real-world error cannot be measured without ground truth.",
                                **demo_data.truth_check(str(out_dir / "orthophoto_georef.tif"), truth)}
        report["validation"]["roads_vs_truth"] = demo_data.road_truth_eval(
            scored, str(Path(truth).parent / "truth_slide_mask.tif"), grid, p["buffer_m"], p["blocked_frac"])

    s = time.perf_counter()
    brief.make_figure(out_dir / "map_preview.png", o_al, v_al, mask, scored, grid)
    T.lap("6_brief_figure", s)
    s = time.perf_counter()
    report["processing_time_s"] = dict(T.t)
    report["processing_time_s"]["total_so_far"] = T.total()
    brief.make_pdf(out_dir / "brief.pdf", report, blocked, out_dir / "map_preview.png")
    T.lap("7_pdf", s)
    report["processing_time_s"] = {**T.t, "total": T.total()}
    report["processing_time_statement"] = (
        f"{valid_km2:.2f} km2 analysed at {grid_res:g} m/px, {report['hardware']['cpu_count']} CPU core(s), "
        f"{report['hardware']['ram_gb']} GB RAM, no GPU: {T.total():.0f} s (this pipeline only; photogrammetry "
        f"stitching time is measured separately).")
    # regenerate the PDF once so the printed processing time includes everything except the PDF itself
    brief.make_pdf(out_dir / "brief.pdf", report, blocked, out_dir / "map_preview.png")
    export_csv(blocked + uncertain, out_dir / "blocked_and_uncertain_stretches.csv")
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    return report


def export_csv(rows, path):
    import csv
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["status", "road", "length_m", "mean_changed_frac"])
        for r in rows:
            w.writerow([r["status"], r["road"], r["length_m"], r["mean_changed_frac"]])
