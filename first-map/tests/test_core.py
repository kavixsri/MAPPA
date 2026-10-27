import numpy as np
import cv2
from affine import Affine
from rasterio.transform import from_origin

from mappa import georef, planner, roads
from mappa.demo_data import fbm
from mappa.export import corrected_transform


def _scene(seed=0, n=500):
    rng = np.random.default_rng(seed)
    g = fbm(rng, (n, n), [30, 12, 5, 2], [1, 1, 1, 1])
    rgb = np.dstack([g * 255, np.roll(g, 7, 0) * 200, np.roll(g, 13, 1) * 160]).astype(np.float32)
    return rgb


def test_registration_recovers_known_shift():
    base = _scene()
    M_true = np.float64([[1, 0, 6.0], [0, 1, -4.0]])         # ortho px -> base px
    inv = cv2.invertAffineTransform(M_true)
    ortho = cv2.warpAffine(base, inv, (500, 500), flags=cv2.INTER_LINEAR)
    ones = np.ones((500, 500), bool)
    M, info = georef.register(ortho * 0.9 + 10, ones, base, ones, 1.0)
    assert info["method"].startswith("SIFT")
    assert abs(M[0, 2] - 6.0) < 0.3 and abs(M[1, 2] + 4.0) < 0.3


def test_corrected_transform_identity_and_shift():
    G = from_origin(1000, 2000, 1.0, 1.0)
    T = from_origin(1000, 2000, 0.1, 0.1)
    assert np.allclose(list(corrected_transform(T, G, np.float64([[1, 0, 0], [0, 1, 0]])))[:6], list(T)[:6])
    # base px = ortho px + 5 px east  ->  ortho must move +5 m east
    T2 = corrected_transform(T, G, np.float64([[1, 0, 5], [0, 1, 0]]))
    assert abs((T2 * (0, 0))[0] - 1005.0) < 1e-6 and abs((T2 * (0, 0))[1] - 2000.0) < 1e-6


def test_road_classification_rules():
    p = roads.DEFAULTS
    assert roads.classify(0.8, 1.2, True, p) == roads.BLOCKED
    assert roads.classify(0.8, 0.1, True, p) == roads.UNCERTAIN      # big colour change, no height confirmation
    assert roads.classify(0.05, 2.0, True, p) == roads.CLEAR
    assert roads.classify(0.5, None, False, p) == roads.UNCERTAIN     # no DSM: need >= 60% to call blocked
    assert roads.classify(0.7, None, False, p) == roads.BLOCKED


def test_flight_plan_numbers_are_sane():
    p = planner.plan(600, 500, 90)
    assert 2.0 < p["gsd_cm_px"] < 4.0
    assert p["max_speed_ms"] > 2 and p["n_images"] > 100
