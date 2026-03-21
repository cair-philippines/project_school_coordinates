#!/bin/bash
# Copies parquet data into the locator directory for Docker build.
# Run this before deploying to Cloud Run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_SRC="$SCRIPT_DIR/../data/modified"
DATA_DST="$SCRIPT_DIR/data/modified"

mkdir -p "$DATA_DST"
cp "$DATA_SRC/public_school_coordinates.parquet" "$DATA_DST/"
cp "$DATA_SRC/private_school_coordinates.parquet" "$DATA_DST/"

echo "Data copied to $DATA_DST"
ls -lh "$DATA_DST"
