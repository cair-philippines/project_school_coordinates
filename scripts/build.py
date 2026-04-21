"""Unified entry point for the unified school coordinates pipeline.

Three stages, selectable via --stage:

    silver   — preprocess all bronze files, materialize data/silver/
    gold     — cascade + crosswalk + validation + fallback, write data/gold/
    all      — run silver then gold (default)

Examples:
    python scripts/build.py --stage=all      # full rebuild
    python scripts/build.py --stage=silver   # just materialize silver
    python scripts/build.py --stage=gold     # silver → gold (assumes silver exists)

The previously-standalone scripts/build_coordinates.py and
scripts/build_private_coordinates.py are now internal modules driven from
here via main().
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules import (
    load_monitoring,
    load_osmapaaralan,
    load_nsbi,
    load_geolocation,
    load_drrms,
    load_psgc,
    load_enrollment,
    load_private_tosf,
    load_sos_mapping,
)


def stage_silver(project_root):
    """Preprocess every bronze source into silver parquets."""
    print("=" * 60)
    print("STAGE: silver (preprocess bronze → silver)")
    print("=" * 60)
    root = str(project_root)

    # Enrollment must come first — it's consumed by build_crosswalk's
    # 7-digit reconciliation during the gold stage (via silver, so the
    # crosswalk build doesn't care, but it's cheap to order logically).
    print("\n[enrollment]")
    load_enrollment.preprocess(root)

    print("\n[psgc_crosswalk]")
    load_psgc.preprocess(root)

    print("\n[sos_mapping]")
    load_sos_mapping.preprocess(root)

    print("\n[monitoring]")
    load_monitoring.preprocess(root)

    print("\n[osmapaaralan]")
    load_osmapaaralan.preprocess(root)

    print("\n[nsbi]")
    load_nsbi.preprocess(root)

    print("\n[geolocation]")
    load_geolocation.preprocess(root)

    print("\n[drrms]")
    load_drrms.preprocess(root)

    print("\n[private_tosf]")
    load_private_tosf.preprocess(root)

    print("\nSilver stage complete.\n")


def stage_gold(project_root):
    """Read silver, run public + private coordinate pipelines, write data/gold/."""
    print("=" * 60)
    print("STAGE: gold (silver → gold)")
    print("=" * 60)

    # Public pipeline
    print("\n--- Public pipeline ---")
    from scripts import build_coordinates as public_pipeline
    public_pipeline.main()

    # Private pipeline
    print("\n--- Private pipeline ---")
    from scripts import build_private_coordinates as private_pipeline
    private_pipeline.main()

    print("\nGold stage complete.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Build the unified school coordinates datasets."
    )
    parser.add_argument(
        "--stage",
        choices=["all", "silver", "gold"],
        default="all",
        help="Which stage(s) to run. Default: all.",
    )
    args = parser.parse_args()

    if args.stage in ("all", "silver"):
        stage_silver(PROJECT_ROOT)

    if args.stage in ("all", "gold"):
        stage_gold(PROJECT_ROOT)

    print("Done.")


if __name__ == "__main__":
    main()
