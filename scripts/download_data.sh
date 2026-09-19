#!/usr/bin/env bash
# Download the public source datasets EcoTwin analyses.
#
# The files are served from the competition's public S3 prefix. Bucket listing
# is denied, so the file names below are the verified object keys.
set -euo pipefail

DEST="${1:-data/raw/power_laws_forecasting}"
BASE="https://s3.amazonaws.com/drivendata/data/51/public"
FILES=(train.csv metadata.csv weather.csv holidays.csv)

mkdir -p "$DEST"
for f in "${FILES[@]}"; do
  if [[ -s "$DEST/$f" ]]; then
    echo "[data] $f already present, skipping"
    continue
  fi
  echo "[data] downloading $f ..."
  curl -fSL --retry 4 --retry-delay 2 -o "$DEST/$f" "$BASE/$f"
done

echo "[data] done. Now run: python scripts/inspect_data.py && python scripts/prepare_data.py"
