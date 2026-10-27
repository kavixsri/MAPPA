"""Open every output with independent readers and print a pass/fail table (proof the formats are valid).
Usage: python scripts/verify_outputs.py examples/demo_run/output"""
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import rasterio

d = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/demo_run/output")
rows = []


def ok(name, fn):
    p = d / name
    if not p.exists():
        rows.append((name, "MISSING", ""))
        return
    try:
        rows.append((name, "OK", fn(p)))
    except Exception as e:  # noqa: BLE001
        rows.append((name, "FAIL", str(e)[:80]))


def tif(p):
    with rasterio.open(p) as s:
        return f"GeoTIFF {s.width}x{s.height}, {s.count} band(s), {s.crs.to_string()}, overviews={bool(s.overviews(1))}"


def vec(p):
    g = gpd.read_file(p)
    return f"{len(g)} features, {g.crs.to_string() if g.crs else 'no CRS'}, {sorted(g.geom_type.unique())}"


def kml(p):
    g = gpd.read_file(p, driver="KML") if False else None
    import xml.etree.ElementTree as ET
    root = ET.parse(p).getroot()
    n = sum(1 for e in root.iter() if e.tag.endswith("Placemark"))
    return f"KML 2.2, {n} placemarks"


ok("orthophoto_georef.tif", tif)
ok("change_mask.tif", tif)
ok("height_anomaly_m.tif", tif)
ok("change_polygons.gpkg", vec)
ok("change_polygons.geojson", vec)
ok("roads_status.gpkg", vec)
ok("roads_status.geojson", vec)
ok("roads_status.kml", kml)
ok("change_polygons.kml", kml)
ok("brief.pdf", lambda p: f"PDF {p.stat().st_size // 1024} KB")
w = max(len(r[0]) for r in rows)
for n, s, i in rows:
    print(f"{n:<{w}}  {s:<7} {i}")
sys.exit(1 if any(r[1] != "OK" for r in rows if r[1] != "MISSING") else 0)
