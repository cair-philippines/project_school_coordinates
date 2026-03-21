"""Private School Coordinates Pipeline — Orchestrator.

Loads the Private School Seats and TOSF data collection, cleans self-reported
coordinates, merges with the LIS universe, expands from enrollment data,
tags enrollment status, and writes the canonical output.

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
from modules import load_private_tosf, load_enrollment, load_psgc, validate_psgc

OUTPUT_DATA_DIR = PROJECT_ROOT / "data" / "modified"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "output"

# Enrollment files for universe expansion + status tagging (add paths here)
ENROLLMENT_FILES = [
    PROJECT_ROOT / "data" / "raw" / "SY_2024_2025_School_Level_Data_on_Official_Enrollment.csv",
]


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

    print(f"\nMerged result (LIS): {len(result):,} schools")
    print(f"  With coordinates:    {with_coords:,}")
    print(f"  Without coordinates: {without_coords:,}")

    return result


# ---------------------------------------------------------------------------
# Step 2.5: Enrollment-based universe expansion
# ---------------------------------------------------------------------------
def expand_from_enrollment(result):
    """Add private schools from enrollment that are not in the LIS universe."""
    base_count = len(result)
    universe_ids = set(result["school_id"])

    additions = []
    for filepath in ENROLLMENT_FILES:
        if not filepath.exists():
            print(f"  Enrollment file not found, skipping: {filepath.name}")
            continue
        enroll_df = load_enrollment.load(str(filepath), sector="private")
        missing = enroll_df[~enroll_df["school_id"].isin(universe_ids)]
        missing = missing.drop_duplicates(subset="school_id", keep="first")
        if len(missing) > 0:
            additions.append(missing)
            print(f"\nEnrollment expansion:")
            print(f"  {filepath.name}: {len(missing):,} private schools not in LIS universe")

    if not additions:
        print(f"\nEnrollment expansion: 0 new schools")
        return result

    new_schools = pd.concat(additions, ignore_index=True)
    new_schools = new_schools.drop_duplicates(subset="school_id", keep="first")
    # Only add schools truly not in result
    new_schools = new_schools[~new_schools["school_id"].isin(universe_ids)]

    # Build rows matching result schema
    new_rows = pd.DataFrame(columns=result.columns)
    for col in result.columns:
        if col in new_schools.columns:
            new_rows[col] = new_schools[col].values
        else:
            new_rows[col] = None

    new_rows["coord_status"] = "no_coords"
    new_rows["coord_rejection_reason"] = "not_in_lis"
    for col in ["esc_participating", "shsvp_participating", "jdvp_participating"]:
        new_rows[col] = 0

    # Ensure consistent dtypes before concat
    for col in ["latitude", "longitude"]:
        new_rows[col] = pd.to_numeric(new_rows[col], errors="coerce")
    for col in ["esc_participating", "shsvp_participating", "jdvp_participating"]:
        new_rows[col] = new_rows[col].astype(int)

    result = pd.concat([result, new_rows], ignore_index=True)
    print(f"  Final universe: {len(result):,} (+{len(result) - base_count:,} from enrollment)")

    return result


# ---------------------------------------------------------------------------
# Step 3: Tag enrollment status
# ---------------------------------------------------------------------------
def tag_enrollment_status(result):
    """Tag each school with enrollment status from enrollment files."""
    all_enrolled = set()
    for filepath in ENROLLMENT_FILES:
        if not filepath.exists():
            continue
        ids = load_enrollment.get_enrollment_ids(str(filepath), sector="private")
        all_enrolled.update(ids)

    result["enrollment_status"] = result["school_id"].apply(
        lambda x: "active" if x in all_enrolled else "no_enrollment_reported"
    )
    # Schools added from enrollment are by definition active
    not_in_lis = result["coord_rejection_reason"] == "not_in_lis"
    result.loc[not_in_lis, "enrollment_status"] = "active"

    active = (result["enrollment_status"] == "active").sum()
    no_enroll = (result["enrollment_status"] == "no_enrollment_reported").sum()
    print(f"\nEnrollment status:")
    print(f"  active: {active:,}")
    print(f"  no_enrollment_reported: {no_enroll:,}")
    return result


# ---------------------------------------------------------------------------
# Step 4: Validation & Report
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

    lines.append(f"\nTotal private schools: {total:,}")
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

    lines.append(f"\nEnrollment status:")
    for status, count in result["enrollment_status"].value_counts().items():
        lines.append(f"  {status}: {count:,}")

    lines.append(f"\nGASTPE participation (among submitting schools):")
    lines.append(f"  ESC:     {result['esc_participating'].sum():,}")
    lines.append(f"  SHS VP:  {result['shsvp_participating'].sum():,}")
    lines.append(f"  JDVP:    {result['jdvp_participating'].sum():,}")

    lines.append(f"\nRegional distribution:")
    for region, count in result["region"].value_counts(dropna=False).head(18).items():
        label = region if region is not None else "(no region)"
        with_c = result[(result["region"] == region) & result["coord_status"].isin(["valid", "fixed_swap"])].shape[0]
        pct = f"{100*with_c/count:.0f}%" if count > 0 else "N/A"
        lines.append(f"  {label}: {count:,} schools, {with_c:,} with coords ({pct})")

    report = "\n".join(lines)
    print(f"\n{report}")

    OUTPUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_REPORT_DIR / "build_private_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {report_path}")
    return report


# ---------------------------------------------------------------------------
# Step 5: Output
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
        "enrollment_status",
        "psgc_region",
        "psgc_region_name",
        "psgc_province",
        "psgc_province_name",
        "psgc_municity",
        "psgc_municity_name",
        "psgc_barangay",
        "psgc_barangay_name",
        "psgc_observed_barangay",
        "psgc_validation",
        "urban_rural",
        "income_class",
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
        {"field": "  Enrollment expansion", "value": "SY 2024-2025 enrollment data — adds schools not in LIS"},
        {"field": "", "value": ""},
        {"field": "Coordinate Cleaning", "value": ""},
        {"field": "  Pass 1", "value": "Fix swapped lat/lon (lon in PH lat range AND lat in PH lon range)"},
        {"field": "  Pass 2", "value": "Reject invalid (null, non-finite, abs>90/180, zero)"},
        {"field": "  Pass 3", "value": "Reject out-of-PH bounds (lat not in [4.5, 21.5], lon not in [116, 127])"},
        {"field": "", "value": ""},
        {"field": "Enrollment Status", "value": ""},
        {"field": "  active", "value": "School has reported enrollment in SY 2024-2025"},
        {"field": "  no_enrollment_reported", "value": "School in LIS/TOSF but no enrollment in SY 2024-2025"},
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
def append_psgc(result):
    """Join PSGC crosswalk and run spatial validation."""
    root = str(PROJECT_ROOT)

    print("\nAppending PSGC codes...")
    psgc = load_psgc.load(root)
    print(f"  PSGC crosswalk: {len(psgc):,} schools")

    result = result.merge(psgc, on="school_id", how="left")
    matched = result["psgc_barangay"].notna().sum()
    print(f"  Matched: {matched:,} / {len(result):,}")

    print("\nSpatial validation (point-in-polygon)...")
    result = validate_psgc.spatial_lookup(root, result)
    result = validate_psgc.validate(result)

    return result


def main():
    universe, coords, clean_stats = load_sources()
    result = merge(universe, coords)
    result = expand_from_enrollment(result)
    result = tag_enrollment_status(result)
    result = append_psgc(result)
    validate_and_report(result, clean_stats)
    write_output(result)
    print("\nDone.")


if __name__ == "__main__":
    main()
