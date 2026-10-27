"""Synthetic demo scene with KNOWN ground truth, so the georeferencing error can be measured honestly.

Generates (all clearly SIMULATED):
  base_before_wgs84.tif   coarse 'last known state' imagery (EPSG:4326, season/lighting shifted)
  drone_after_ortho.tif   0.5 m/px 'drone orthomosaic' of the scene after a simulated landslide,
                          with a deliberately wrong GPS-only georeference (offset + small rotation)
  dsm_after.tif / dem_base.tif   photogrammetry DSM (with vertical bias) and a coarse DEM
  roads_osm_like.geojson  road centrelines
  truth.json              the injected georeference error and landslide footprints"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import LineString, mapping

PX = 0.5          # drone ortho pixel size (m)
N = 2400          # px -> 1.2 km square
LON0, LAT0 = 78.95, 30.30   # arbitrary mountain-valley location, scene is synthetic
EPSG = 32644


def fbm(rng, shape, sigmas, weights):
    out = np.zeros(shape, np.float32)
    for s, w in zip(sigmas, weights):
        n = rng.standard_normal(shape).astype(np.float32)
        out += w * cv2.GaussianBlur(n, (0, 0), s) * s            # scale so octaves have similar amplitude
    out -= out.min()
    return out / max(out.max(), 1e-6)


# road centrelines in metres from top-left (x east, y south)
ROADS = {
    "NH-7 Main Road": [(0, 700), (300, 640), (600, 560), (900, 600), (1200, 480)],
    "Village Road": [(200, 1200), (330, 900), (450, 760), (600, 560)],
    "Valley Link": [(600, 560), (700, 300), (850, 100), (900, 0)],
    "Hill Track": [(0, 1000), (250, 1050), (500, 1100), (800, 1000), (1200, 1050)],
    "Ridge Road": [(900, 600), (1000, 900), (1100, 1200)],
}
SLIDES = {  # centre x, centre y, half-width, half-height (m)
    "slide_A_crosses_NH7": (445, 560, 30, 190),
    "slide_B_beside_Hill_Track": (800, 984, 20, 22),
    "slide_C_hillside_no_road": (1010, 250, 28, 40),
}


def _px(v):
    return int(round(v / PX))


def generate(out_dir: str, seed: int = 7, base_res_m: float = 10.0, gps_dx: float = 4.2, gps_dy: float = -3.1,
             gps_rot_deg: float = 0.3, dsm_bias_m: float = 12.3):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
    e0, n0 = to_utm.transform(LON0, LAT0)
    e0, n0 = round(e0 / 10) * 10, round(n0 / 10) * 10
    true_tf = from_origin(e0, n0, PX, PX)
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)

    # --- terrain colour -----------------------------------------------------------------
    v = fbm(rng, (N, N), [90, 40, 18, 8, 3, 1.2], [1, 1, 1, 1, 1, 0.8])
    soil = fbm(rng, (N, N), [70, 25, 9], [1, 1, 1])
    t = np.clip((v - 0.2) * 1.8, 0, 1)[..., None]
    veg = (1 - t) * np.array([38, 78, 34]) + t * np.array([122, 132, 62])
    s = np.clip((soil - 0.55) * 4, 0, 1)[..., None]
    img = (1 - s) * veg + s * np.array([150, 122, 84])
    img = img.astype(np.uint8)
    for _ in range(26):                                             # field parcels
        x, y = rng.integers(0, N - 200, 2)
        w, h = rng.integers(60, 200, 2)
        tint = rng.integers(-28, 28, 3)
        img[y:y + h, x:x + w] = np.clip(img[y:y + h, x:x + w].astype(int) + tint, 0, 255)
    river = [(1200, 880), (900, 840), (600, 900), (400, 1000), (250, 1130), (100, 1300), (0, 1350)]
    cv2.polylines(img, [np.array([[_px(x), _px(y)] for x, y in river])], False, (96, 120, 140), _px(10), cv2.LINE_AA)
    for name, pts in ROADS.items():
        poly = np.array([[_px(x), _px(y)] for x, y in pts])
        cv2.polylines(img, [poly], False, (190, 186, 178), _px(8.5), cv2.LINE_AA)
        cv2.polylines(img, [poly], False, (118, 116, 112), _px(6), cv2.LINE_AA)
    for _ in range(22):                                             # buildings near roads
        name = list(ROADS)[rng.integers(0, len(ROADS))]
        pts = ROADS[name]
        a = pts[rng.integers(0, len(pts))]
        bx, by = a[0] + rng.integers(-60, 60), a[1] + rng.integers(-60, 60)
        bw, bh = rng.integers(8, 18), rng.integers(8, 16)
        col = [(176, 96, 74), (200, 196, 188), (150, 150, 158)][rng.integers(0, 3)]
        cv2.rectangle(img, (_px(bx), _px(by)), (_px(bx + bw), _px(by + bh)), col, -1)
    img = np.clip(img.astype(np.float32) + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
    before = img.copy()

    # --- landslides ---------------------------------------------------------------------
    edge = fbm(rng, (N, N), [20, 8, 3], [1, 1, 0.7]) - 0.5
    mound = fbm(rng, (N, N), [14, 5], [1, 1])
    slide_mask = np.zeros((N, N), bool)
    truth_slides = {}
    for name, (cx, cy, hw, hh) in SLIDES.items():
        d = ((xx * PX - cx) / hw) ** 2 + ((yy * PX - cy) / hh) ** 2
        m = d < (1 + 0.55 * edge * 2)
        slide_mask |= m
        truth_slides[name] = dict(cx=cx, cy=cy, half_w=hw, half_h=hh)
    tex = fbm(rng, (N, N), [5, 2, 0.8], [1, 1, 1])[..., None]
    debris = (1 - tex) * np.array([96, 78, 60]) + tex * np.array([156, 144, 128])
    debris += rng.normal(0, 6, debris.shape)
    after = before.astype(np.float32)
    after[slide_mask] = debris[slide_mask]
    after = np.clip(after, 0, 255).astype(np.uint8)

    with rasterio.open(out / "truth_slide_mask.tif", "w", height=N, width=N, count=1, dtype="uint8",
                       transform=true_tf, crs=f"EPSG:{EPSG}", compress="deflate") as d:
        d.write(slide_mask.astype(np.uint8), 1)

    # --- DEM / DSM ----------------------------------------------------------------------
    terrain = 1500 + 45 * fbm(rng, (N, N), [700, 350], [1, 1]) - 0.02 * yy * PX
    dsm_h = terrain + 0.12 * rng.standard_normal((N, N)).astype(np.float32) + 0.25 * fbm(rng, (N, N), [4], [1])
    dsm_h = dsm_h + slide_mask * (1.6 + 1.8 * mound)
    dsm_h = dsm_h + dsm_bias_m
    dsm_1m = cv2.resize(dsm_h.astype(np.float32), (N // 2, N // 2), interpolation=cv2.INTER_AREA)
    dem_30 = cv2.resize(terrain.astype(np.float32), (int(N * PX / 30), int(N * PX / 30)), interpolation=cv2.INTER_AREA)

    # --- GPS-only georeference error on the drone products -----------------------------------
    centre = true_tf * (N / 2, N / 2)
    bad_tf = Affine.translation(gps_dx, gps_dy) @ Affine.rotation(gps_rot_deg, centre) @ true_tf
    prof = dict(driver="GTiff", crs=f"EPSG:{EPSG}", compress="deflate")
    with rasterio.open(out / "drone_after_ortho.tif", "w", height=N, width=N, count=4, dtype="uint8",
                       transform=bad_tf, tiled=True, blockxsize=256, blockysize=256, **prof) as d:
        d.write(np.dstack([after, np.full((N, N), 255, np.uint8)]).transpose(2, 0, 1))
        d.build_overviews([2, 4, 8], Resampling.average)
    bad_tf_dsm = Affine.translation(gps_dx, gps_dy) @ Affine.rotation(gps_rot_deg, centre) @ from_origin(e0, n0, 1.0, 1.0)
    with rasterio.open(out / "dsm_after.tif", "w", height=N // 2, width=N // 2, count=1, dtype="float32",
                       transform=bad_tf_dsm, nodata=-9999, **prof) as d:
        d.write(dsm_1m, 1)
    with rasterio.open(out / "dem_base.tif", "w", height=dem_30.shape[0], width=dem_30.shape[1], count=1,
                       dtype="float32", transform=from_origin(e0, n0, 30.0, 30.0), nodata=-9999, **prof) as d:
        d.write(dem_30, 1)

    # --- base imagery: older, coarser, different season/lighting, correct georeference ----------
    b = before.astype(np.float32)
    b = 255 * (b / 255) ** np.array([0.88, 0.95, 1.05]) * np.array([1.06, 1.02, 0.94]) + 6
    b += rng.normal(0, 2, b.shape)
    k = int(round(base_res_m / PX))
    bc = cv2.resize(np.clip(b, 0, 255).astype(np.uint8), (N // k, N // k), interpolation=cv2.INTER_AREA)
    base_tf = from_origin(e0, n0, base_res_m, base_res_m)
    dst_tf, w, h = calculate_default_transform(f"EPSG:{EPSG}", "EPSG:4326", bc.shape[1], bc.shape[0],
                                               *rasterio.transform.array_bounds(bc.shape[0], bc.shape[1], base_tf))
    with rasterio.open(out / "base_before_wgs84.tif", "w", driver="GTiff", height=h, width=w, count=4, dtype="uint8",
                       crs="EPSG:4326", transform=dst_tf, compress="deflate") as d:
        for i in range(3):
            reproject(bc[..., i], rasterio.band(d, i + 1), src_transform=base_tf, src_crs=f"EPSG:{EPSG}",
                      dst_transform=dst_tf, dst_crs="EPSG:4326", resampling=Resampling.bilinear)
        reproject(np.full(bc.shape[:2], 255, np.uint8), rasterio.band(d, 4), src_transform=base_tf,
                  src_crs=f"EPSG:{EPSG}", dst_transform=dst_tf, dst_crs="EPSG:4326", resampling=Resampling.nearest)

    # --- roads (OSM-like) -----------------------------------------------------------------
    to_ll = Transformer.from_crs(EPSG, 4326, always_xy=True)
    feats = []
    for name, pts in ROADS.items():
        ll = [to_ll.transform(e0 + x, n0 - y) for x, y in pts]
        feats.append({"type": "Feature", "properties": {"name": name, "highway": "secondary"},
                      "geometry": mapping(LineString(ll))})
    (out / "roads_osm_like.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    truth = dict(origin_utm=[e0, n0], epsg=EPSG, injected_gps_dx_m=gps_dx, injected_gps_dy_m=gps_dy,
                 injected_rotation_deg=gps_rot_deg, injected_dsm_vertical_bias_m=dsm_bias_m, slides=truth_slides,
                 base_res_m=base_res_m, seed=seed,
                 true_transform=list(true_tf)[:6], bad_transform=list(bad_tf)[:6])
    (out / "truth.json").write_text(json.dumps(truth, indent=2))
    cv2.imwrite(str(out / "preview_before.jpg"), cv2.cvtColor(before, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
    cv2.imwrite(str(out / "preview_after.jpg"), cv2.cvtColor(after, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
    return {k: str(out / v) for k, v in dict(ortho="drone_after_ortho.tif", base="base_before_wgs84.tif",
                                              roads="roads_osm_like.geojson", dsm="dsm_after.tif",
                                              dem="dem_base.tif", truth="truth.json").items()}


def truth_check(corrected_ortho: str, truth_path: str) -> dict:
    """Compare the pipeline's corrected georeference with the true one at a 5x5 grid of image points."""
    tr = json.loads(Path(truth_path).read_text())
    true_tf = Affine(*tr["true_transform"])
    with rasterio.open(corrected_ortho) as ds:
        new_tf = ds.transform
        w, h = ds.width, ds.height
    errs, before = [], []
    bad = Affine(*tr["bad_transform"])
    for i in np.linspace(0, w, 5):
        for j in np.linspace(0, h, 5):
            tx, ty = true_tf * (i, j)
            nx, ny = new_tf * (i, j)
            bx, by = bad * (i, j)
            errs.append(np.hypot(nx - tx, ny - ty))
            before.append(np.hypot(bx - tx, by - ty))
    errs, before = np.array(errs), np.array(before)
    return dict(error_before_mean_m=round(float(before.mean()), 2), error_before_max_m=round(float(before.max()), 2),
                error_after_mean_m=round(float(errs.mean()), 2), error_after_max_m=round(float(errs.max()), 2),
                error_after_rms_m=round(float(np.sqrt((errs ** 2).mean())), 2), n_points=int(len(errs)))


def road_truth_eval(scored, truth_mask_path: str, grid, buffer_m: float = 5.0, blocked_frac: float = 0.40) -> dict:
    """Score predicted BLOCKED segments against the synthetic truth (segment is truly blocked if >= 40% of its
    buffer lies inside the true slide footprint). Lengths in metres."""
    import math
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, transform as wt
    from rasterio.warp import Resampling as Rs
    tm = np.zeros(grid.shape, np.uint8)
    with rasterio.open(truth_mask_path) as src:
        reproject(rasterio.band(src, 1), tm, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=grid.transform, dst_crs=grid.crs, resampling=Rs.nearest)
    truth_blocked = []
    for g in scored.geometry:
        buf = g.buffer(buffer_m, cap_style=2)
        l, b, r, t = buf.bounds
        inv = ~grid.transform
        c0, r1 = inv * (l, b)
        c1, r0 = inv * (r, t)
        c0, c1 = max(0, int(math.floor(c0))), min(grid.width, int(math.ceil(c1)))
        r0, r1 = max(0, int(math.floor(r0))), min(grid.height, int(math.ceil(r1)))
        if c1 <= c0 or r1 <= r0:
            truth_blocked.append(False)
            continue
        ins = ~geometry_mask([buf], out_shape=(r1 - r0, c1 - c0), transform=wt(Window(c0, r0, c1 - c0, r1 - r0), grid.transform))
        truth_blocked.append(bool(ins.any() and tm[r0:r1, c0:c1][ins].mean() >= blocked_frac))
    tb = np.array(truth_blocked)
    pb = (scored.status == "BLOCKED").values
    L = scored.length_m.values
    tp, fp, fn = L[tb & pb].sum(), L[~tb & pb].sum(), L[tb & ~pb].sum()
    pu = (scored.status == "UNCERTAIN").values
    return dict(true_blocked_m=round(float(L[tb].sum())), predicted_blocked_m=round(float(L[pb].sum())),
                true_positive_m=round(float(tp)), false_positive_m=round(float(fp)), false_negative_m=round(float(fn)),
                false_negative_but_flagged_uncertain_m=round(float(L[tb & ~pb & pu].sum())),
                precision=round(float(tp / (tp + fp)), 2) if tp + fp else None,
                recall=round(float(tp / (tp + fn)), 2) if tp + fn else None)
