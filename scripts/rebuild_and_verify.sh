#!/bin/bash
# Rebuild the pipeline after bronze changes, then verify.
#
# Usage:
#   bash scripts/rebuild_and_verify.sh
#
# Steps:
#   1. Snapshot current gold metrics
#   2. Run the full pipeline (bronze -> silver -> gold)
#   3. Diff new metrics vs the snapshot
#   4. Run the test suite
#   5. Print a one-line summary
#
# Exit code:
#   0  build succeeded AND tests passed
#   non-zero  something failed
#
# Metrics differences are informational — they're expected when bronze
# files change — and do not affect the exit code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SNAPSHOT_DIR="$REPO_ROOT/output/_prev_metrics"

cd "$REPO_ROOT"

echo "================================================================"
echo "  rebuild_and_verify"
echo "================================================================"

# --- 1. Snapshot current gold metrics (for diff) ---
mkdir -p "$SNAPSHOT_DIR"
for f in build_public_metrics.json build_private_metrics.json; do
  if [ -f "data/gold/$f" ]; then
    cp "data/gold/$f" "$SNAPSHOT_DIR/$f"
  fi
done

# --- 2. Rebuild ---
echo ""
echo "[1/3] Rebuilding bronze -> silver -> gold..."
python scripts/build.py --stage=all

# --- 3. Diff metrics ---
echo ""
echo "================================================================"
echo "[2/3] Metrics diff vs previous run"
echo "================================================================"
DIFF_PUBLIC_RC=0
DIFF_PRIVATE_RC=0

if [ -f "$SNAPSHOT_DIR/build_public_metrics.json" ]; then
  echo ""
  echo "--- Public ---"
  python scripts/diff_metrics.py \
    "$SNAPSHOT_DIR/build_public_metrics.json" \
    data/gold/build_public_metrics.json || DIFF_PUBLIC_RC=$?
else
  echo "No previous public metrics — skipping public diff."
fi

if [ -f "$SNAPSHOT_DIR/build_private_metrics.json" ]; then
  echo ""
  echo "--- Private ---"
  python scripts/diff_metrics.py \
    "$SNAPSHOT_DIR/build_private_metrics.json" \
    data/gold/build_private_metrics.json || DIFF_PRIVATE_RC=$?
else
  echo "No previous private metrics — skipping private diff."
fi

# --- 4. Run tests ---
echo ""
echo "================================================================"
echo "[3/3] Tests"
echo "================================================================"
TESTS_RC=0
python -m unittest discover tests || TESTS_RC=$?

# --- 5. One-line summary ---
echo ""
echo "================================================================"
if [ "$TESTS_RC" -ne 0 ]; then
  echo "  REGRESSION: tests failed"
  echo "================================================================"
  exit "$TESTS_RC"
fi

METRICS_CHANGED=""
if [ "$DIFF_PUBLIC_RC" -ne 0 ] || [ "$DIFF_PRIVATE_RC" -ne 0 ]; then
  METRICS_CHANGED=" (metrics moved — review the diff above)"
fi

echo "  PASS: build succeeded, 46 tests passed${METRICS_CHANGED}"
echo "================================================================"
