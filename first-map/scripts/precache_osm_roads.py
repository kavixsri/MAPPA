"""Pre-cache OpenStreetMap roads for a bounding box (run ONCE while online, before any disaster).
Usage: python scripts/precache_osm_roads.py south west north east roads.geojson
NOTE: written against the public Overpass API; not exercised in the build sandbox (no outbound access)."""
import json
import sys
import urllib.parse
import urllib.request

s, w, n, e, out = sys.argv[1:6]
q = f'[out:json][timeout:60];way["highway"]({s},{w},{n},{e});out geom;'
req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": q}).encode(),
                             headers={"User-Agent": "mappa-precache/0.1"})
data = json.load(urllib.request.urlopen(req, timeout=120))
feats = []
for el in data["elements"]:
    if el["type"] == "way" and "geometry" in el and len(el["geometry"]) > 1:
        feats.append({"type": "Feature",
                      "properties": {"name": el.get("tags", {}).get("name") or el["tags"].get("highway", "road"),
                                     "highway": el.get("tags", {}).get("highway"), "osm_id": el["id"]},
                      "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in el["geometry"]]}})
json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
print(f"{len(feats)} road ways -> {out}  (c) OpenStreetMap contributors, ODbL")
