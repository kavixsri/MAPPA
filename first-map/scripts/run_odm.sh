#!/usr/bin/env bash
# Stitch with OpenDroneMap (open source), fully offline once the docker image is pulled.
# Usage: scripts/run_odm.sh datasets/odm_data_aukerman/project [orthophoto-resolution-cm]
# Time it:  the script prints wall-clock seconds. THAT is the number to quote (with image count + your laptop spec).
set -euo pipefail
PROJ="$(cd "$1" && pwd)"; RES="${2:-5}"
N=$(ls "$PROJ/images" | wc -l)
START=$(date +%s)
docker run --rm -v "$(dirname "$PROJ")":/datasets opendronemap/odm \
  --project-path /datasets "$(basename "$PROJ")" \
  --fast-orthophoto --dsm --orthophoto-resolution "$RES" --skip-3dmodel --max-concurrency "$(nproc)"
END=$(date +%s)
echo "ODM: $N images, $((END-START)) s, $(nproc) cores, orthophoto ${RES} cm/px"
echo "$N images, $((END-START)) s, $(nproc) cores" > "$PROJ/odm_timing.txt"
echo "ortho: $PROJ/odm_orthophoto/odm_orthophoto.tif   dsm: $PROJ/odm_dem/dsm.tif"
