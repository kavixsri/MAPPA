# MAPPA — the first map after the landslide

Offline, laptop-only workflow that turns consumer-drone photos into a **georeferenced current map**, compares it with the **last known state from open imagery**, and reports **what changed and which roads are blocked**. No cloud, no ground control points, no GPU.

> Hackathon problem statement: *"The First Map After The Landslide"* — responders need a current map in hours, not after the next satellite pass.

![map preview](examples/demo_run/output/map_preview.png)

## How it works

```
 drone photos ──► OpenDroneMap (--fast-orthophoto, --dsm) ──► orthophoto + DSM   (GPS-only georeference)
                                                                   │
 pre-cached base imagery (Sentinel-2 / OAM) ─────────────────────► │ 1. SIFT + RANSAC registration to base  → GCP-free georef + honest error budget
 pre-cached OSM roads, Copernicus DEM ───────────────────────────► │ 2. radiometric normalise → colour change  (+ DSM−DEM height anomaly)
                                                                   │ 3. 20 m road segments, 5 m buffer → BLOCKED / UNCERTAIN / CLEAR
                                                                   ▼
        GeoTIFF · GeoPackage · GeoJSON · KML · CSV · one-page PDF brief with the accuracy statement
```

| Stage | Open-source tool |
|---|---|
| Stitching, orthomosaic, DSM | [OpenDroneMap](https://github.com/OpenDroneMap/ODM) |
| Feature matching / registration | OpenCV (SIFT, RANSAC) |
| Raster & vector I/O, reprojection | rasterio (GDAL), GeoPandas, Shapely, pyproj |
| Base data (pre-cached once) | Sentinel-2 or [OpenAerialMap](https://openaerialmap.org), OpenStreetMap roads, Copernicus DEM |
| Brief & map | Matplotlib, ReportLab |
| Viewing outputs | QGIS (any GIS opens them) |

## Quick start (everything offline after install)

```bash
pip install -r requirements.txt
python -m pytest -q                       # 4 tests
python -m mappa demo --out my_demo        # SIMULATED scene with known ground truth, ~5 s
python scripts/verify_outputs.py my_demo/output
```

Real data:

```bash
# once, while online (before the disaster): public sample drone photos, OSM roads
bash scripts/get_odm_sample.sh odm_data_aukerman
python scripts/precache_osm_roads.py <south> <west> <north> <east> roads.geojson

# stitch (needs Docker + the opendronemap/odm image pulled once)
bash scripts/run_odm.sh datasets/odm_data_aukerman/project 5      # prints measured seconds

# map, compare, score roads
python -m mappa run --ortho datasets/odm_data_aukerman/project/odm_orthophoto/odm_orthophoto.tif \
    --dsm datasets/odm_data_aukerman/project/odm_dem/dsm.tif --dem copernicus_dem.tif \
    --base sentinel2_before.tif --roads roads.geojson --base-accuracy 10 --out out
```

Pilot tools: `python -m mappa card` (one-page capture card) and `python -m mappa plan --lat .. --lon ..` (flight numbers + lawnmower KML).

## Capture protocol (the 30-second card → [`capture_card.pdf`](capture_card.pdf))
GPS lock → 80–100 m, camera straight down → interval photos every 2 s, 75 % forward / 65 % side overlap → one oblique loop round the slide → land at launch point. A pre-loaded KML grid means the pilot only presses start.

## Outputs (`examples/demo_run/output/`)
`orthophoto_georef.tif` · `change_mask.tif` · `height_anomaly_m.tif` · `change_polygons.{gpkg,geojson,kml}` · `roads_status.{gpkg,geojson,kml}` · `blocked_and_uncertain_stretches.csv` · `brief.pdf` · `report.json` (all numbers, thresholds, timings, hardware).

## Honest accuracy statement

* **Absolute position:** consumer-drone GPS alone is typically a few metres. After registration to base imagery the absolute error is bounded by the **base layer** (Sentinel-2 geolocation is of the order of 10 m, so MAPPA defaults to **±10 m, 95 %** and says "unverified against ground truth"). Pass `--base-accuracy` to change the assumption.
* **Relative accuracy inside the map** (distances, shapes) is far better than absolute, but was **not measured** here.
* **Change detection is coarse**: limited by the base imagery resolution (10 m for Sentinel-2). Small debris will not be resolved. **Colour alone is not enough**: in the synthetic ablation, colour-only detection found *none* of the debris-covered road (debris and bare road look alike) and, with a 20 m base, raised false alarms. The DSM−DEM height cue is what makes "BLOCKED" work, so a DSM (ODM `--dsm`) and a DEM should always be pre-cached ([`docs/ablation.md`](docs/ablation.md)).
* **Thresholds** (40 % changed + 0.5 m height ⇒ BLOCKED; 15 % ⇒ UNCERTAIN) are untuned defaults, not field-calibrated.

## What has and has not been verified

| Claim | Status |
|---|---|
| Pipeline runs end-to-end offline, outputs open in rasterio/GeoPandas/XML parsers | ✅ tested (`docs/format_check.txt`) |
| Registration recovers an injected GPS error on a **synthetic** scene | ✅ 5.7 m → 0.1–0.5 m (10 m base), up to 2.7 m with a 20 m base ([`docs/ablation.md`](docs/ablation.md)) |
| Road precision / recall vs known truth | ✅ **synthetic only** — not a field result |
| Processing time | ✅ measured for the post-ODM pipeline: see `report.json` (1.43 km² in a few seconds, 1 core). **ODM stitching time is NOT measured in this repo** — run `scripts/run_odm.sh` on your laptop and quote that |
| ODM stitching on real photos | ⚠️ scripts provided; **not executed in the build sandbox (no Docker)** |
| Behaviour on a real landslide / real Sentinel-2 / real OSM | ⚠️ **not yet tested** — next step. Use OpenAerialMap post-disaster imagery or your own flight |
| Opening outputs in QGIS | ⚠️ formats are standard and machine-verified; add your own QGIS screenshot to `docs/` |

The demo data is **simulated and labelled as such everywhere** (including a banner on the PDF brief). The OpenDroneMap sample datasets that exist on GitHub are `odm_data_aukerman`, `odm_data_toledo` and `odm_data_bellus`.

## Repo layout
```
mappa/        grid.py georef.py change.py roads.py export.py brief.py pipeline.py demo_data.py planner.py cli.py
scripts/      run_odm.sh get_odm_sample.sh precache_osm_roads.py verify_outputs.py ablation.py
tests/        test_core.py
docs/         METHOD.md ablation.md format_check.txt MAPPA_deck.pptx/.pdf media/ (walkthrough video)
examples/     demo_run/ (inputs + outputs of the simulated scene), mission_example.kml
capture_card.pdf
```

MIT licensed. OSM data © OpenStreetMap contributors (ODbL). Sentinel-2 / Copernicus DEM: Copernicus open licence.
