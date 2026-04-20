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
    PROJECT_ROOT / "data" / "raw" / "project_bukas_enrollment_2024-25.csv",
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

    print(f"\nCoordinate cleaning (Passes 1-3):")
    print(f"  Fixed swapped lat/lon: {clean_stats['fixed_swap']:,}")
    print(f"  Rejected invalid:      {clean_stats['rejected_invalid']:,}")
    print(f"  Rejected out-of-bounds: {clean_stats['rejected_out_of_bounds']:,}")

    print(f"\nSuspect coordinate detection (Pass 4):")
    print(f"  Placeholder defaults:  {clean_stats.get('suspect_placeholder', 0):,}")
    print(f"  Coordinate clusters:   {clean_stats.get('suspect_cluster', 0):,}")
    print(f"  Round coordinates:     {clean_stats.get('suspect_round', 0):,}")
    print(f"  Total suspect:         {clean_stats.get('suspect_total', 0):,}")

    print(f"\n  Valid after all passes: {clean_stats['valid']:,}")

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
        "old_region",
        "division",
        "province",
        "municipality",
        "barangay",
        "esc_participating",
        "shsvp_participating",
        "jdvp_participating",
        "enrollment_status",
        "school_management",
        "annex_status",
        "offers_es",
        "offers_jhs",
        "offers_shs",
        "shs_strand_offerings",
        "psgc_region",
        "psgc_region_name",
        "psgc_province",
        "psgc_province_name",
        "psgc_municity",
        "psgc_municity_name",
        "psgc_barangay",
        "psgc_barangay_name",
        "psgc_observed_barangay",
        "psgc_observed_municity",
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
    psgc_match = (out["psgc_validation"] == "psgc_match").sum()
    psgc_mismatch = (out["psgc_validation"] == "psgc_mismatch").sum()
    psgc_no_val = (out["psgc_validation"] == "psgc_no_validation").sum()
    active = (out["enrollment_status"] == "active").sum()
    no_enroll = (out["enrollment_status"] == "no_enrollment_reported").sum()

    metadata = pd.DataFrame([
        # --- Overview ---
        {"field": "Pipeline", "value": "Private School Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Source File", "value": "Private School Seats and TOSF ao 2025Oct27.xlsx"},
        {"field": "Total Schools", "value": f"{len(out):,}"},
        {"field": "With Coordinates", "value": f"{with_coords:,}"},
        {"field": "Without Coordinates", "value": f"{len(out) - with_coords:,}"},
        {"field": "", "value": ""},

        # --- Column Dictionary ---
        {"field": "COLUMN DICTIONARY", "value": ""},
        {"field": "school_id", "value": "Validated BEIS School ID (corrected by DepEd where applicable)"},
        {"field": "school_name", "value": "Official LIS school name"},
        {"field": "latitude", "value": "Cleaned latitude (WGS84). Null if coordinates were rejected or not submitted."},
        {"field": "longitude", "value": "Cleaned longitude (WGS84). Null if coordinates were rejected or not submitted."},
        {"field": "coord_status", "value": "Coordinate quality status (see Coordinate Status below)"},
        {"field": "coord_rejection_reason", "value": "If coord_status=no_coords: why coordinates are missing (see Rejection Reasons below)"},
        {"field": "region", "value": "DepEd administrative region (NIR-aware, from enrollment file)"},
        {"field": "old_region", "value": "DepEd region (pre-NIR naming; Negros Occidental in Region VI, Negros Oriental/Siquijor in Region VII)"},
        {"field": "division", "value": "DepEd division (from LIS master list)"},
        {"field": "province", "value": "Province (from LIS master list)"},
        {"field": "municipality", "value": "City or municipality (from LIS master list)"},
        {"field": "barangay", "value": "Barangay (from LIS master list)"},
        {"field": "esc_participating", "value": "Education Service Contracting program participation (1=yes, 0=no or not submitted)"},
        {"field": "shsvp_participating", "value": "Senior High School Voucher Program participation (1=yes, 0=no or not submitted)"},
        {"field": "jdvp_participating", "value": "Joint Delivery Voucher Program participation (1=yes, 0=no or not submitted)"},
        {"field": "enrollment_status", "value": "Whether the school reported enrollment in SY 2024-2025 (see Enrollment Status below)"},
        {"field": "school_management", "value": "School management type (e.g., 'DepEd', 'Non-Sectarian', 'Sectarian', 'SUC', 'LUC'). From enrollment file."},
        {"field": "annex_status", "value": "Annex classification (e.g., 'Standalone School', 'Mother School', 'Annex/Extension School'). From enrollment file."},
        {"field": "offers_es", "value": "Whether the school offers Elementary (True/False). From enrollment file."},
        {"field": "offers_jhs", "value": "Whether the school offers Junior High School (True/False). From enrollment file."},
        {"field": "offers_shs", "value": "Whether the school offers Senior High School (True/False). From enrollment file."},
        {"field": "shs_strand_offerings", "value": "Comma-delimited SHS strand offerings (e.g., 'ABM,HUMSS,STEM'). Null if school does not offer SHS."},
        {"field": "psgc_region", "value": "10-digit PSA Philippine Standard Geographic Code for region"},
        {"field": "psgc_region_name", "value": "PSA official region name"},
        {"field": "psgc_province", "value": "10-digit PSGC for province"},
        {"field": "psgc_province_name", "value": "PSA official province name"},
        {"field": "psgc_municity", "value": "10-digit PSGC for municipality/city"},
        {"field": "psgc_municity_name", "value": "PSA official municipality/city name"},
        {"field": "psgc_barangay", "value": "10-digit PSGC for barangay (CLAIMED — from school-to-PSGC crosswalk, Q4 2024)"},
        {"field": "psgc_barangay_name", "value": "PSA official barangay name (claimed)"},
        {"field": "psgc_observed_barangay", "value": "10-digit PSGC for barangay (OBSERVED — from point-in-polygon against Q4 2025 shapefile). Which barangay the school's coordinates actually fall in."},
        {"field": "psgc_observed_municity", "value": "7-digit PSGC for municipality (OBSERVED — from the same point-in-polygon). Null if coordinate falls outside all polygons (over water)."},
        {"field": "psgc_validation", "value": "Result of comparing claimed vs observed barangay (see PSGC Validation below)"},
        {"field": "urban_rural", "value": "Urban or Rural classification based on 2020 Census of Population and Housing"},
        {"field": "income_class", "value": "Municipal income classification (1st through 5th class) based on DOF D.O. 74, S. 2024"},
        {"field": "", "value": ""},

        # --- Data Sources ---
        {"field": "DATA SOURCES", "value": ""},
        {"field": "  Universe", "value": "SCHOOLS WITHOUT SUBMISSION sheet — LIS master list (Sep 2025, 12,011 schools)"},
        {"field": "  Coordinates", "value": "RAW DATA sheet — self-reported via Google Forms (Oct 2025, 9,632 submissions)"},
        {"field": "  Enrollment expansion", "value": "SY 2024-2025 enrollment data — adds private schools not in LIS"},
        {"field": "", "value": ""},

        # --- Coordinate Status ---
        {"field": "COORDINATE STATUS (coord_status values)", "value": ""},
        {"field": "  valid", "value": "Coordinates passed all cleaning checks. Self-reported — accuracy not guaranteed."},
        {"field": "  fixed_swap", "value": "Latitude and longitude were swapped in the submission and auto-corrected."},
        {"field": "  no_coords", "value": "No usable coordinates. See coord_rejection_reason for why."},
        {"field": "", "value": ""},

        # --- Rejection Reasons ---
        {"field": "REJECTION REASONS (coord_rejection_reason values)", "value": ""},
        {"field": "  no_submission", "value": "School exists in LIS but did not submit the TOSF Google Form."},
        {"field": "  invalid", "value": "Submitted coordinates were non-numeric, non-finite, >90/>180, or zero."},
        {"field": "  out_of_bounds", "value": "Submitted coordinates fell outside Philippines bounding box [4.5-21.5, 116-127]."},
        {"field": "  not_in_lis", "value": "School found in enrollment data but not in the LIS master list. No TOSF submission possible."},
        {"field": "", "value": ""},

        # --- Coordinate Cleaning ---
        {"field": "COORDINATE CLEANING (applied in order)", "value": ""},
        {"field": "  Pass 1", "value": "Fix swapped lat/lon (lon in PH lat range AND lat in PH lon range)"},
        {"field": "  Pass 2", "value": "Reject invalid (null, non-finite, abs>90/180, zero)"},
        {"field": "  Pass 3", "value": "Reject out-of-PH bounds (lat not in [4.5, 21.5], lon not in [116, 127])"},
        {"field": "", "value": ""},

        # --- Enrollment Status ---
        {"field": "ENROLLMENT STATUS (enrollment_status values)", "value": ""},
        {"field": f"  active ({active:,} schools)", "value": "School has reported enrollment in SY 2024-2025."},
        {"field": f"  no_enrollment_reported ({no_enroll:,} schools)", "value": "School in LIS/TOSF but no enrollment in SY 2024-2025. May have ceased operations or not yet reported."},
        {"field": "", "value": ""},

        # --- PSGC Validation ---
        {"field": "PSGC VALIDATION (psgc_validation values)", "value": ""},
        {"field": f"  psgc_match ({psgc_match:,} schools)", "value": "Coordinates fall within the claimed PSGC barangay polygon. Coordinates and admin assignment are consistent."},
        {"field": f"  psgc_mismatch ({psgc_mismatch:,} schools)", "value": "Coordinates fall in a DIFFERENT barangay than claimed. Higher rate for private schools due to self-reported coordinates."},
        {"field": f"  psgc_no_validation ({psgc_no_val:,} schools)", "value": "Cannot validate. School has no coordinates, no PSGC code, or coordinates fall outside all barangay polygons."},
        {"field": "", "value": ""},
        {"field": "PSGC NOTE", "value": "Claimed PSGC codes are from Q4 2024. Observed codes are from Q4 2025 shapefile. Some mismatches may be due to PSGC changes between quarters rather than coordinate errors."},
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
    """Join PSGC crosswalk, backfill blank names, and run spatial validation."""
    root = str(PROJECT_ROOT)

    print("\nAppending PSGC codes...")
    psgc = load_psgc.load(root)
    print(f"  PSGC crosswalk: {len(psgc):,} schools")

    result = result.merge(psgc, on="school_id", how="left")
    matched = result["psgc_barangay"].notna().sum()
    print(f"  PSGC matched: {matched:,} / {len(result):,}")

    # Backfill blank school names from PSGC crosswalk
    blank_name = result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")
    has_psgc_name = result["psgc_school_name"].notna() & (result["psgc_school_name"] != "None")
    backfill_mask = blank_name & has_psgc_name
    result.loc[backfill_mask, "school_name"] = result.loc[backfill_mask, "psgc_school_name"]
    print(f"  School names backfilled from PSGC: {backfill_mask.sum():,}")
    remaining_blank = (result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")).sum()
    print(f"  Still blank after backfill: {remaining_blank:,}")

    # Drop the temporary psgc_school_name column
    result = result.drop(columns=["psgc_school_name"], errors="ignore")

    print("\nSpatial validation (point-in-polygon)...")
    result = validate_psgc.spatial_lookup(root, result)
    # Municipal validation must run BEFORE barangay validation so coord_status
    # is populated when the barangay check decides whether to trust coords.
    result = validate_psgc.validate_municipality(result, project_root=root)
    result = validate_psgc.validate(result)

    return result


def enrich_from_enrollment(result):
    """Enrich schools with metadata from the enrollment file."""
    print("\nEnriching from enrollment metadata...")
    for filepath in ENROLLMENT_FILES:
        if not filepath.exists():
            continue
        meta = load_enrollment.load_full_metadata(str(filepath))
        print(f"  Enrollment metadata: {len(meta):,} schools")

        meta_indexed = meta.set_index("school_id")

        # Backfill school_name where still blank
        blank_name = result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")
        in_meta = result["school_id"].isin(meta_indexed.index)
        backfill_name = blank_name & in_meta
        if backfill_name.sum() > 0:
            fill_ids = result.loc[backfill_name, "school_id"]
            result.loc[backfill_name, "school_name"] = meta_indexed.loc[
                fill_ids.values, "school_name"
            ].values
            print(f"  School names backfilled from enrollment: {backfill_name.sum():,}")

        # Add new columns
        enroll_cols = [
            "school_management", "annex_status",
            "offers_es", "offers_jhs", "offers_shs", "shs_strand_offerings",
        ]
        for col in enroll_cols:
            if col not in result.columns:
                result[col] = None
            matched = result["school_id"].isin(meta_indexed.index)
            fill_ids = result.loc[matched, "school_id"]
            if len(fill_ids) > 0 and col in meta_indexed.columns:
                result.loc[matched, col] = meta_indexed.loc[
                    fill_ids.values, col
                ].values

        # Add region (NIR-aware) and old_region
        if "old_region" not in result.columns:
            result["old_region"] = result["region"]

        result["region_new"] = None
        matched = result["school_id"].isin(meta_indexed.index)
        fill_ids = result.loc[matched, "school_id"]
        if len(fill_ids) > 0:
            result.loc[matched, "region_new"] = meta_indexed.loc[
                fill_ids.values, "region"
            ].values

        no_new_region = result["region_new"].isna() | (result["region_new"] == "None")
        result.loc[no_new_region, "region_new"] = result.loc[no_new_region, "old_region"]

        no_old = result["old_region"].isna() | (result["old_region"] == "None")
        in_meta_old = no_old & result["school_id"].isin(meta_indexed.index)
        if in_meta_old.sum() > 0:
            fill_ids = result.loc[in_meta_old, "school_id"]
            result.loc[in_meta_old, "old_region"] = meta_indexed.loc[
                fill_ids.values, "old_region"
            ].values

        result["region"] = result["region_new"]
        result = result.drop(columns=["region_new"])

        print(f"  Enriched: {matched.sum():,} / {len(result):,}")

    remaining_blank = (result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")).sum()
    print(f"  Remaining blank school names: {remaining_blank:,}")

    return result


def main():
    universe, coords, clean_stats = load_sources()
    result = merge(universe, coords)
    result = expand_from_enrollment(result)
    result = tag_enrollment_status(result)
    result = append_psgc(result)
    result = enrich_from_enrollment(result)
    validate_and_report(result, clean_stats)
    write_output(result)
    print("\nDone.")


if __name__ == "__main__":
    main()
