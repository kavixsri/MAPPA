#!/usr/bin/env bash
# Download a public OpenDroneMap sample drone dataset (raw photos with GPS EXIF). Needs internet ONCE, before the "disaster".
# Datasets that exist: odm_data_aukerman, odm_data_toledo, odm_data_bellus  (github.com/OpenDroneMap/<name>)
set -euo pipefail
NAME="${1:-odm_data_aukerman}"
mkdir -p datasets/"$NAME"
git clone --depth 1 "https://github.com/OpenDroneMap/$NAME" datasets/"$NAME"/src
mkdir -p datasets/"$NAME"/project/images
cp datasets/"$NAME"/src/images/* datasets/"$NAME"/project/images/ 2>/dev/null || cp datasets/"$NAME"/src/*.[jJ][pP]*[gG] datasets/"$NAME"/project/images/
echo "images: $(ls datasets/$NAME/project/images | wc -l)  ->  datasets/$NAME/project"
