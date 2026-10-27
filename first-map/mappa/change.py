"""Change detection between the co-registered drone ortho and the last-known base imagery.

Colour change: radiometric normalisation (quantile-matched linear fit, so season/sun differences
don't read as change) -> blur both to the base layer's native resolution -> RGB distance ->
robust threshold (median + k*MAD) -> morphology -> minimum area.
Height change (optional): DSM (from ODM) minus DEM (e.g. Copernicus), with the vertical bias between
the two removed using the median of unchanged ground. Both are reported; the DEM comparison only
supports the decision (trees/buildings also show up in DSM-DEM)."""
from __future__ import annotations

import cv2
import numpy as np


def radiometric_normalise(ortho: np.ndarray, base: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = ortho.copy()
    q = np.linspace(5, 95, 19)
    for c in range(3):
        qa = np.percentile(ortho[..., c][valid], q)
        qb = np.percentile(base[..., c][valid], q)
        A = np.vstack([qa, np.ones_like(qa)]).T
        gain, bias = np.linalg.lstsq(A, qb, rcond=None)[0]
        out[..., c] = np.clip(ortho[..., c] * gain + bias, 0, 255)
    return out


def colour_change(ortho, base, valid, res_m, base_res_m, k=5.0, floor=22.0, min_area_m2=150.0):
    sigma = max(0.8, base_res_m / res_m / 2.0)
    o = cv2.GaussianBlur(radiometric_normalise(ortho, base, valid), (0, 0), sigma)
    b = cv2.GaussianBlur(base, (0, 0), sigma)
    d = np.sqrt(((o - b) ** 2).sum(axis=2)).astype(np.float32)
    dv = d[valid]
    med = float(np.median(dv))
    mad = float(np.median(np.abs(dv - med)) * 1.4826)
    thr = max(med + k * mad, floor)
    m = ((d > thr) & valid).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    m = remove_small(m, int(min_area_m2 / res_m ** 2))
    return m.astype(bool), d, {"diff_threshold": thr, "diff_median": med, "diff_mad": mad, "k": k,
                               "blur_sigma_px": sigma}


def remove_small(mask_u8: np.ndarray, min_px: int) -> np.ndarray:
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    return keep[lab].astype(np.uint8)


def height_anomaly(dsm: np.ndarray, dem: np.ndarray, colour_mask: np.ndarray, valid: np.ndarray):
    """Return (anomaly_m, vertical_bias_m). Bias = median(DSM-DEM) over valid, unchanged ground."""
    diff = dsm - dem
    ok = valid & np.isfinite(diff) & ~cv2.dilate(colour_mask.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    bias = float(np.median(diff[ok])) if ok.any() else 0.0
    return (diff - bias).astype(np.float32), bias


def combine(colour_mask, anomaly, valid, res_m, height_change_m=1.0, min_area_m2=150.0):
    if anomaly is None:
        return colour_mask, None
    hm = (np.abs(np.nan_to_num(anomaly)) >= height_change_m) & valid
    hm = cv2.morphologyEx(hm.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    hm = remove_small(hm, int(min_area_m2 / res_m ** 2)).astype(bool)
    return colour_mask | hm, hm
