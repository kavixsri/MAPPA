"""GCP-free georeferencing refinement: register the drone ortho (GPS-only georef) to open base imagery.

Method: SIFT features on contrast-normalised grayscale -> ratio-test matches -> RANSAC similarity
(rotation + uniform scale + translation). Residual of RANSAC inliers feeds the honest error budget.
Fallback: FFT phase correlation (translation only)."""
from __future__ import annotations

import cv2
import numpy as np


def _prep(gray: np.ndarray, valid: np.ndarray, blur_px: float) -> np.ndarray:
    g = gray.astype(np.float32)
    if blur_px > 0.3:
        g = cv2.GaussianBlur(g, (0, 0), blur_px)
    lo, hi = np.percentile(g[valid], [1, 99]) if valid.any() else (0, 255)
    g = np.clip((g - lo) / max(hi - lo, 1e-3), 0, 1)
    g8 = (g * 255).astype(np.uint8)
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g8)


def register(ortho_rgb, ortho_valid, base_rgb, base_valid, res_m: float, blur_px: float = 0.0):
    """Return (M, info). M is 2x3, maps ortho grid px -> base grid px."""
    go = cv2.cvtColor(np.clip(ortho_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(np.clip(base_rgb, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    a, b = _prep(go, ortho_valid, blur_px), _prep(gb, base_valid, blur_px)
    ma = cv2.erode(ortho_valid.astype(np.uint8) * 255, np.ones((15, 15), np.uint8))
    mb = cv2.erode(base_valid.astype(np.uint8) * 255, np.ones((15, 15), np.uint8))
    sift = cv2.SIFT_create(nfeatures=10000)
    ka, da = sift.detectAndCompute(a, ma)
    kb, db = sift.detectAndCompute(b, mb)
    info = {"n_kp_ortho": len(ka), "n_kp_base": len(kb)}
    if da is not None and db is not None and len(ka) > 20 and len(kb) > 20:
        pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.8 * p[1].distance]
        info["n_matches"] = len(good)
        if len(good) >= 12:
            src = np.float32([ka[m.queryIdx].pt for m in good])
            dst = np.float32([kb[m.trainIdx].pt for m in good])
            M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.5,
                                                 maxIters=10000, confidence=0.999)
            if M is not None and inl is not None and int(inl.sum()) >= 10:
                scale = float(np.hypot(M[0, 0], M[1, 0]))
                if 0.9 < scale < 1.1:
                    inl = inl.ravel().astype(bool)
                    proj = src[inl] @ M[:, :2].T + M[:, 2]
                    resid = np.linalg.norm(proj - dst[inl], axis=1) * res_m
                    info.update(method="SIFT+RANSAC similarity", n_inliers=int(inl.sum()),
                                inlier_ratio=float(inl.mean()), rms_m=float(np.sqrt((resid ** 2).mean())),
                                p95_resid_m=float(np.percentile(resid, 95)), scale=scale,
                                rotation_deg=float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))))
                    return M.astype(np.float64), info
    (sx, sy), resp = cv2.phaseCorrelate(a.astype(np.float32), b.astype(np.float32))
    M = np.array([[1, 0, -sx], [0, 1, -sy]], np.float64)
    info.update(method="phase-correlation (fallback)", n_inliers=0, rms_m=float("nan"),
                p95_resid_m=float("nan"), scale=1.0, rotation_deg=0.0, response=float(resp))
    return M, info


def shift_m(M: np.ndarray, shape, res_m: float) -> float:
    """Mean displacement (m) the correction applies across the frame = size of the GPS-only error."""
    h, w = shape
    pts = np.array([[w / 2, h / 2], [0, 0], [w, 0], [0, h], [w, h]], np.float64)
    moved = pts @ M[:, :2].T + M[:, 2]
    return float(np.linalg.norm(moved - pts, axis=1).mean() * res_m)


def accuracy95(info: dict, base_acc95_m: float, res_m: float) -> float:
    """Honest 95% horizontal error bound: base-layer absolute accuracy (dominant) combined in
    quadrature with 2x registration RMS. If registration fell back, assume a conservative 3 px RMS."""
    rms = info.get("rms_m")
    if rms is None or np.isnan(rms):
        rms = 3 * res_m
    return float(np.sqrt(base_acc95_m ** 2 + (2.0 * rms) ** 2))
