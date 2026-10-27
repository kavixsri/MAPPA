"""Blocked-road scoring: split OSM road lines into short segments, buffer, and measure how much of each
buffer falls inside the change mask (and, if available, how large the height anomaly is)."""
from __future__ import annotations

import math

import geopandas as gpd
import numpy as np
from rasterio.features import geometry_mask
from rasterio.windows import Window, transform as win_transform
from shapely.geometry import LineString, MultiLineString
from shapely.ops import substring

BLOCKED, UNCERTAIN, CLEAR, NODATA = "BLOCKED", "UNCERTAIN", "CLEAR", "NO_DATA"

DEFAULTS = dict(seg_len_m=20.0, buffer_m=5.0, blocked_frac=0.40, uncertain_frac=0.15,
                blocked_height_m=0.5, blocked_frac_no_dsm=0.60, min_valid=0.5)


def load_roads(path: str, crs) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    if g.crs is None:
        g = g.set_crs(4326)
    g = g.to_crs(crs)
    g = g[g.geometry.notna() & g.geometry.geom_type.isin(["LineString", "MultiLineString"])].explode(index_parts=False)
    g = g.reset_index(drop=True)
    g["road_id"] = g.index
    if "name" not in g.columns:
        g["name"] = None
    g["name"] = g["name"].fillna(g["highway"] if "highway" in g.columns else "road").astype(str)
    return g


def segments(roads: gpd.GeoDataFrame, seg_len: float) -> gpd.GeoDataFrame:
    rows = []
    for _, r in roads.iterrows():
        line: LineString = r.geometry
        n = max(1, int(math.ceil(line.length / seg_len)))
        step = line.length / n
        for i in range(n):
            seg = substring(line, i * step, (i + 1) * step)
            if seg.length > 0:
                rows.append(dict(road_id=int(r.road_id), name=r["name"], seq=i, length_m=seg.length, geometry=seg))
    return gpd.GeoDataFrame(rows, crs=roads.crs)


def score(segs: gpd.GeoDataFrame, mask: np.ndarray, anomaly, valid: np.ndarray, grid, **kw) -> gpd.GeoDataFrame:
    p = {**DEFAULTS, **kw}
    have_h = anomaly is not None
    H, W = mask.shape
    out = []
    for _, s in segs.iterrows():
        buf = s.geometry.buffer(p["buffer_m"], cap_style=2)
        l, b, r, t = buf.bounds
        inv = ~grid.transform
        c0, r1 = inv * (l, b)
        c1, r0 = inv * (r, t)
        c0, c1 = int(max(0, math.floor(c0))), int(min(W, math.ceil(c1)))
        r0, r1 = int(max(0, math.floor(r0))), int(min(H, math.ceil(r1)))
        status, frac, hmean, vfrac = NODATA, np.nan, np.nan, 0.0
        if c1 > c0 and r1 > r0:
            win = Window(c0, r0, c1 - c0, r1 - r0)
            inside = ~geometry_mask([buf], out_shape=(r1 - r0, c1 - c0), transform=win_transform(win, grid.transform))
            n = int(inside.sum())
            if n:
                v = valid[r0:r1, c0:c1][inside]
                vfrac = float(v.mean())
                if vfrac >= p["min_valid"]:
                    frac = float(mask[r0:r1, c0:c1][inside][v].mean())
                    if have_h:
                        a = np.abs(anomaly[r0:r1, c0:c1][inside][v])
                        hmean = float(np.nanmean(a)) if np.isfinite(a).any() else np.nan
                    status = classify(frac, hmean, have_h, p)
        out.append(dict(road_id=s.road_id, name=s["name"], seq=s.seq, length_m=round(s.length_m, 1),
                        changed_frac=round(frac, 3) if frac == frac else None,
                        height_anom_m=round(hmean, 2) if hmean == hmean else None,
                        valid_frac=round(vfrac, 2), status=status, geometry=s.geometry))
    return gpd.GeoDataFrame(out, crs=segs.crs)


def classify(frac, hmean, have_h, p):
    if have_h and hmean == hmean:
        if frac >= p["blocked_frac"] and hmean >= p["blocked_height_m"]:
            return BLOCKED
        if frac >= p["uncertain_frac"]:
            return UNCERTAIN
        return CLEAR
    if frac >= p["blocked_frac_no_dsm"]:
        return BLOCKED
    if frac >= p["uncertain_frac"]:
        return UNCERTAIN
    return CLEAR


def stretches(scored: gpd.GeoDataFrame, status: str = BLOCKED) -> list[dict]:
    """Merge consecutive same-status segments on one road into reportable stretches (WGS84 centroid)."""
    res = []
    for rid, g in scored.sort_values(["road_id", "seq"]).groupby("road_id"):
        run = []
        for _, s in g.iterrows():
            if s.status == status and (not run or s.seq == run[-1].seq + 1):
                run.append(s)
            else:
                if run:
                    res.append(_pack(run, status))
                run = [s] if s.status == status else []
        if run:
            res.append(_pack(run, status))
    return sorted(res, key=lambda r: -r["length_m"])


def _pack(run, status):
    geom = MultiLineString([r.geometry for r in run])
    return dict(road=run[0]["name"], road_id=int(run[0].road_id), status=status,
                length_m=round(sum(r.length_m for r in run), 1),
                mean_changed_frac=round(float(np.nanmean([r.changed_frac for r in run])), 2),
                _centroid_xy=(geom.centroid.x, geom.centroid.y))
