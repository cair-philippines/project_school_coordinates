"""Private School Coordinates Pipeline — Orchestrator.

Loads the Private School Seats and TOSF data collection, cleans self-reported
coordinates, merges with the LIS universe, and writes the canonical output.

Usage:
    cd project_coordinates/
    python scripts/build_private_coordinates.py

(Run via `ds python3 scripts/build_private_coordinates.py` from the devcontainer.)
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from modules import load_private_tosf

OUTPUT_DATA_DIR = PROJECT_ROOT / "data" / "modified"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "output"


# ---------------------------------------------------------------------------
# Step 1: Load sources
# ---------------------------------------------------------------------------
def load_sources():
    """Load universe and coordinates from TOSF file."""
    root = str(PROJECT_ROOT)

    print("Loading private school sources...")
    universe = load_private_tosf.load_universe(root)
    print(f"  Universe (LIS master list): {len(universe):,} schools")

    coords, clean_stats = load_private_tosf.load_coordinates(root)
    print(f"  RAW DATA submissions: {clean_stats['total_submissions']:,} (deduplicated)")

    print(f"\nCoordinate cleaning:")
    print(f"  Fixed swapped lat/lon: {clean_stats['fixed_swap']:,}")
    print(f"  Rejected invalid:      {clean_stats['rejected_invalid']:,}")
    print(f"  Rejected out-of-bounds: {clean_stats['rejected_out_of_bounds']:,}")
    print(f"  Valid after cleaning:  {clean_stats['valid']:,}")

    return universe, coords, clean_stats


# ---------------------------------------------------------------------------
# Step 2: Merge universe + coordinates
# ---------------------------------------------------------------------------
def merge(universe, coords):
    """Left join universe with cleaned coordinates."""
    result = universe.merge(coords, on="school_id", how="left")

    # Schools without submission: set coord_status
    no_submission = result["coord_status"].isna()
    result.loc[no_submission, "coord_status"] = "no_coords"
    result.loc[no_submission, "coord_rejection_reason"] = "no_submission"

    # Fill GASTPE flags with 0 for non-submitting schools
    for col in ["esc_participating", "shsvp_participating", "jdvp_participating"]:
        result[col] = result[col].fillna(0).astype(int)

    with_coords = result["coord_status"].isin(["valid", "fixed_swap"]).sum()
    without_coords = len(result) - with_coords

    print(f"\nMerged result: {len(result):,} schools")
    print(f"  With coordinates:    {with_coords:,}")
    print(f"  Without coordinates: {without_coords:,}")
    print(f"\nCoord status breakdown:")
    print(result["coord_status"].value_counts().to_string())

    return result


# ---------------------------------------------------------------------------
# Step 3: Validation & Report
# ---------------------------------------------------------------------------
def validate_and_report(result, clean_stats):
    """Write build report."""
    lines = []
    lines.append("=" * 60)
    lines.append("PRIVATE SCHOOL COORDINATES — BUILD REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Source: Private School Seats and TOSF ao 2025Oct27.xlsx")

    total = len(result)
    with_coords = result["coord_status"].isin(["valid", "fixed_swap"]).sum()
    without_coords = total - with_coords

    lines.append(f"\nTotal private schools (LIS universe): {total:,}")
    lines.append(f"  With coordinates:    {with_coords:,} ({100*with_coords/total:.1f}%)")
    lines.append(f"  Without coordinates: {without_coords:,} ({100*without_coords/total:.1f}%)")

    lines.append(f"\nCoordinate cleaning:")
    lines.append(f"  Total submissions (deduplicated): {clean_stats['total_submissions']:,}")
    lines.append(f"  Fixed swapped lat/lon:            {clean_stats['fixed_swap']:,}")
    lines.append(f"  Rejected invalid:                 {clean_stats['rejected_invalid']:,}")
    lines.append(f"  Rejected out-of-bounds:           {clean_stats['rejected_out_of_bounds']:,}")
    lines.append(f"  Valid after cleaning:              {clean_stats['valid']:,}")

    lines.append(f"\nCoord status breakdown:")
    for status, count in result["coord_status"].value_counts().items():
        lines.append(f"  {status}: {count:,}")

    lines.append(f"\nRejection reasons (for no_coords):")
    no_coords = result[result["coord_status"] == "no_coords"]
    for reason, count in no_coords["coord_rejection_reason"].value_counts().items():
        lines.append(f"  {reason}: {count:,}")

    lines.append(f"\nGASTPE participation (among submitting schools):")
    lines.append(f"  ESC:     {result['esc_participating'].sum():,}")
    lines.append(f"  SHS VP:  {result['shsvp_participating'].sum():,}")
    lines.append(f"  JDVP:    {result['jdvp_participating'].sum():,}")

    lines.append(f"\nRegional distribution:")
    for region, count in result["region"].value_counts().head(17).items():
        with_c = result[(result["region"] == region) & result["coord_status"].isin(["valid", "fixed_swap"])].shape[0]
        lines.append(f"  {region}: {count:,} schools, {with_c:,} with coords ({100*with_c/count:.0f}%)")

    report = "\n".join(lines)
    print(f"\n{report}")

    OUTPUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_REPORT_DIR / "build_private_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {report_path}")
    return report


# ---------------------------------------------------------------------------
# Step 4: Output
# ---------------------------------------------------------------------------
def write_output(result):
    """Write parquet, CSV, and Excel output."""
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    final_cols = [
        "school_id",
        "school_name",
        "latitude",
        "longitude",
        "coord_status",
        "coord_rejection_reason",
        "region",
        "division",
        "province",
        "municipality",
        "barangay",
        "esc_participating",
        "shsvp_participating",
        "jdvp_participating",
    ]
    out = result[final_cols].sort_values("school_id").reset_index(drop=True)

    # --- Parquet ---
    parquet_path = OUTPUT_DATA_DIR / "private_school_coordinates.parquet"
    out.to_parquet(parquet_path, index=False)

    # --- CSV ---
    csv_path = OUTPUT_DATA_DIR / "private_school_coordinates.csv"
    out.to_csv(csv_path, index=False)

    # --- Excel workbook (2 sheets) ---
    xlsx_path = OUTPUT_DATA_DIR / "private_school_coordinates.xlsx"

    with_coords = out["coord_status"].isin(["valid", "fixed_swap"]).sum()

    metadata = pd.DataFrame([
        {"field": "Pipeline", "value": "Private School Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Source File", "value": "Private School Seats and TOSF ao 2025Oct27.xlsx"},
        {"field": "Total Schools", "value": str(len(out))},
        {"field": "With Coordinates", "value": str(with_coords)},
        {"field": "Without Coordinates", "value": str(len(out) - with_coords)},
        {"field": "", "value": ""},
        {"field": "Data Source", "value": ""},
        {"field": "  Universe", "value": "SCHOOLS WITHOUT SUBMISSION sheet — LIS master list (Sep 2025)"},
        {"field": "  Coordinates", "value": "RAW DATA sheet — self-reported via Google Forms (Oct 2025)"},
        {"field": "", "value": ""},
        {"field": "Coordinate Cleaning", "value": ""},
        {"field": "  Pass 1", "value": "Fix swapped lat/lon (lon in PH lat range AND lat in PH lon range)"},
        {"field": "  Pass 2", "value": "Reject invalid (null, non-finite, abs>90/180, zero)"},
        {"field": "  Pass 3", "value": "Reject out-of-PH bounds (lat not in [4.5, 21.5], lon not in [116, 127])"},
        {"field": "", "value": ""},
        {"field": "GASTPE Flags", "value": ""},
        {"field": "  esc_participating", "value": "Education Service Contracting program (1=yes, 0=no)"},
        {"field": "  shsvp_participating", "value": "Senior High School Voucher Program (1=yes, 0=no)"},
        {"field": "  jdvp_participating", "value": "Joint Delivery Voucher Program (1=yes, 0=no)"},
    ])

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)
        out.to_excel(writer, sheet_name="Private School Coordinates", index=False)

    print(f"\nOutput written:")
    print(f"  {parquet_path} ({len(out):,} rows)")
    print(f"  {csv_path}")
    print(f"  {xlsx_path} (2 sheets)")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    universe, coords, clean_stats = load_sources()
    result = merge(universe, coords)
    validate_and_report(result, clean_stats)
    write_output(result)
    print("\nDone.")


if __name__ == "__main__":
    main()
