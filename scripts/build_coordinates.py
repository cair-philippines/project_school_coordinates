"""Unified School Coordinates Pipeline — Orchestrator.

Loads four DepEd coordinate sources, builds a school ID crosswalk to resolve
historical ID changes, applies a trust-based priority cascade, attaches
administrative location columns, and writes the canonical output.

Usage:
    cd project_coordinates/
    python scripts/build_coordinates.py

(Run via `ds python3 scripts/build_coordinates.py` from the devcontainer.)
"""

import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path so modules/ is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from modules import load_monitoring, load_nsbi, load_geolocation, load_osmapaaralan, load_drrms
from modules import build_crosswalk, load_enrollment, load_psgc, validate_psgc
from modules.utils import (
    COORD_PRIORITY,
    LOCATION_PRIORITY,
    SOURCE_MONITORING,
    haversine_km,
)

OUTPUT_DATA_DIR = PROJECT_ROOT / "data" / "modified"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "output"

# Enrollment files for universe expansion (add paths here as needed)
ENROLLMENT_FILES = [
    PROJECT_ROOT / "data" / "raw" / "project_bukas_enrollment_2024-25.csv",
]


# ---------------------------------------------------------------------------
# Step 1: Load all sources
# ---------------------------------------------------------------------------
def _load_known_private_ids():
    """Collect school IDs known to be private schools.

    Uses the TOSF file (LIS master list of private schools) and the
    enrollment file (private sector). These IDs should not appear in
    the public school output.
    """
    private_ids = set()

    # From TOSF universe (LIS master list of private schools)
    tosf_path = PROJECT_ROOT / "data" / "raw" / "Private School Seats and TOSF ao 2025Oct27.xlsx"
    if tosf_path.exists():
        from modules import load_private_tosf
        universe = load_private_tosf.load_universe(str(PROJECT_ROOT))
        private_ids.update(universe["school_id"].dropna())

    # From enrollment file (private sector)
    for filepath in ENROLLMENT_FILES:
        if filepath.exists():
            enroll = load_enrollment.load(str(filepath), sector="private")
            private_ids.update(enroll["school_id"].dropna())

    return private_ids


def load_all_sources():
    """Load and return a dict of source label -> DataFrame."""
    print("Loading sources...")
    root = str(PROJECT_ROOT)
    sources = {
        "monitoring_validated": load_monitoring.load(root),
        "osmapaaralan": load_osmapaaralan.load(root),
        "nsbi_2324": load_nsbi.load(root),
        "geolocation_deped": load_geolocation.load(root),
        "drrms_imrs": load_drrms.load(root),
    }
    for label, df in sources.items():
        print(f"  {label}: {len(df):,} rows")

    return sources


# ---------------------------------------------------------------------------
# Step 1.5: Build crosswalk and remap source IDs
# ---------------------------------------------------------------------------
def build_and_apply_crosswalk(sources):
    """Build the school ID crosswalk and remap all source DataFrames."""
    root = str(PROJECT_ROOT)
    crosswalk = build_crosswalk.build(root, sources)

    print("\nRemapping source IDs to canonical...")
    remapped_sources = {}
    for label, df in sources.items():
        remapped, count = build_crosswalk.remap_source(df, crosswalk)
        remapped_sources[label] = remapped
        if count > 0:
            print(f"  {label}: {count:,} IDs remapped")

    # Remove known private school IDs AFTER crosswalk remapping
    # (OSMapaaralan contains both public and private footprints, and some
    # private schools use old IDs that only resolve to private after remapping)
    private_ids = _load_known_private_ids()
    if private_ids:
        total_removed = 0
        for label, df in remapped_sources.items():
            before = len(df)
            remapped_sources[label] = df[~df["school_id"].isin(private_ids)].reset_index(drop=True)
            removed = before - len(remapped_sources[label])
            total_removed += removed
            if removed > 0:
                print(f"  {label}: {removed:,} private IDs excluded")
        if total_removed > 0:
            print(f"  Total: {total_removed:,} private school records removed from public sources")

    return remapped_sources, crosswalk


# ---------------------------------------------------------------------------
# Step 2: Establish the school universe (with enrollment expansion)
# ---------------------------------------------------------------------------
def build_school_universe(sources, crosswalk):
    """Union all school_ids across sources, then expand from enrollment files."""
    all_ids = pd.concat(
        [df[["school_id"]].drop_duplicates() for df in sources.values()],
        ignore_index=True,
    ).drop_duplicates(subset="school_id")
    base_count = len(all_ids)
    print(f"\nSchool universe (from coord sources): {base_count:,}")

    # Expand from enrollment files
    enrollment_additions = []
    for filepath in ENROLLMENT_FILES:
        if not filepath.exists():
            print(f"  Enrollment file not found, skipping: {filepath.name}")
            continue
        enroll_df = load_enrollment.load(str(filepath))
        universe_ids = set(all_ids["school_id"])
        missing = load_enrollment.find_missing(enroll_df, universe_ids, crosswalk)
        if len(missing) > 0:
            enrollment_additions.append(missing)
            print(f"  {filepath.name}: {len(missing):,} public schools not in coord sources")

    if enrollment_additions:
        additions = pd.concat(enrollment_additions, ignore_index=True)
        additions = additions.drop_duplicates(subset="school_id", keep="first")
        new_ids = additions[~additions["school_id"].isin(all_ids["school_id"])]
        all_ids = pd.concat(
            [all_ids, new_ids[["school_id"]]],
            ignore_index=True,
        )
        # Store enrollment metadata for location fill later
        build_school_universe._enrollment_meta = additions
    else:
        build_school_universe._enrollment_meta = pd.DataFrame()

    print(f"  Final universe: {len(all_ids):,} (+{len(all_ids) - base_count:,} from enrollment)")
    return all_ids


# ---------------------------------------------------------------------------
# Step 3: Apply coordinate priority cascade
# ---------------------------------------------------------------------------
def apply_coord_cascade(universe, sources):
    """For each school, pick coordinates from the highest-priority source."""
    result = universe.copy()
    result["latitude"] = np.nan
    result["longitude"] = np.nan
    result["coord_source"] = None
    result["monitoring_chosen_source"] = None
    result["sources_available"] = ""

    # Index each source by school_id for fast lookup
    indexed = {}
    for label, df in sources.items():
        deduped = df.drop_duplicates(subset="school_id", keep="first")
        indexed[label] = deduped.set_index("school_id")

    for label in COORD_PRIORITY:
        if label not in indexed:
            continue
        src = indexed[label]
        needs_coords = result["coord_source"].isna()
        fill_ids = result.loc[
            needs_coords & result["school_id"].isin(src.index), "school_id"
        ]

        if len(fill_ids) == 0:
            continue

        matched = src.loc[fill_ids.values]
        idx = result.loc[fill_ids.index].index
        result.loc[idx, "latitude"] = matched["latitude"].values
        result.loc[idx, "longitude"] = matched["longitude"].values
        result.loc[idx, "coord_source"] = label

        if label == SOURCE_MONITORING and "monitoring_chosen_source" in src.columns:
            result.loc[idx, "monitoring_chosen_source"] = (
                matched["monitoring_chosen_source"].values
            )

    # Build sources_available
    for label, src in indexed.items():
        mask = result["school_id"].isin(src.index)
        result.loc[mask, "sources_available"] = result.loc[
            mask, "sources_available"
        ].apply(lambda x, lbl=label: f"{x},{lbl}" if x else lbl)

    print(f"\nCoordinate cascade results:")
    print(result["coord_source"].value_counts(dropna=False).to_string())
    return result


# ---------------------------------------------------------------------------
# Step 4: Attach location columns
# ---------------------------------------------------------------------------
def attach_location(result, sources):
    """Fill region, province, municipality, barangay from best source."""
    loc_cols = ["region", "province", "municipality", "barangay"]
    for col in loc_cols:
        result[col] = None
    result["location_source"] = None

    for label in LOCATION_PRIORITY:
        if label not in sources:
            continue
        src = sources[label].drop_duplicates(subset="school_id", keep="first")
        src_indexed = src.set_index("school_id")

        available_loc_cols = [c for c in loc_cols if c in src_indexed.columns]
        if not available_loc_cols:
            continue

        needs_location = result["location_source"].isna()
        in_source = result["school_id"].isin(src_indexed.index)
        fill_mask = needs_location & in_source
        fill_ids = result.loc[fill_mask, "school_id"]

        if len(fill_ids) == 0:
            continue

        matched = src_indexed.loc[fill_ids.values]
        has_any = matched[available_loc_cols].notna().any(axis=1)
        valid_ids = fill_ids[has_any.values]
        if len(valid_ids) == 0:
            continue

        valid_matched = src_indexed.loc[valid_ids.values]
        idx = result.loc[valid_ids.index].index
        for col in available_loc_cols:
            result.loc[idx, col] = valid_matched[col].values
        result.loc[idx, "location_source"] = label

    # Attach best available school_name
    result["school_name"] = None
    for label in COORD_PRIORITY:
        if label not in sources:
            continue
        src = sources[label].drop_duplicates(subset="school_id", keep="first")
        src_indexed = src.set_index("school_id")
        if "school_name" not in src_indexed.columns:
            continue

        needs_name = result["school_name"].isna()
        in_source = result["school_id"].isin(src_indexed.index)
        fill_ids = result.loc[needs_name & in_source, "school_id"]
        if len(fill_ids) == 0:
            continue
        matched = src_indexed.loc[fill_ids.values]
        has_name = matched["school_name"].notna()
        valid_ids = fill_ids[has_name.values]
        if len(valid_ids) == 0:
            continue
        valid_matched = src_indexed.loc[valid_ids.values]
        idx = result.loc[valid_ids.index].index
        result.loc[idx, "school_name"] = valid_matched["school_name"].values

    # Fill remaining gaps from enrollment metadata (for enrollment-only schools)
    enroll_meta = getattr(build_school_universe, "_enrollment_meta", pd.DataFrame())
    if len(enroll_meta) > 0:
        enroll_indexed = enroll_meta.set_index("school_id")
        enroll_loc_cols = [c for c in loc_cols if c in enroll_indexed.columns]

        needs_location = result["location_source"].isna()
        in_enroll = result["school_id"].isin(enroll_indexed.index)
        fill_mask = needs_location & in_enroll
        fill_ids = result.loc[fill_mask, "school_id"]

        if len(fill_ids) > 0:
            matched = enroll_indexed.loc[fill_ids.values]
            has_any = matched[enroll_loc_cols].notna().any(axis=1)
            valid_ids = fill_ids[has_any.values]
            if len(valid_ids) > 0:
                valid_matched = enroll_indexed.loc[valid_ids.values]
                idx = result.loc[valid_ids.index].index
                for col in enroll_loc_cols:
                    result.loc[idx, col] = valid_matched[col].values
                result.loc[idx, "location_source"] = "enrollment"

    # Tag enrollment-only schools in sources_available
    if len(enroll_meta) > 0:
        enroll_only = result["school_id"].isin(enroll_meta["school_id"]) & (result["coord_source"].isna())
        result.loc[enroll_only, "sources_available"] = "enrollment_only"

    print(f"\nLocation source results:")
    print(result["location_source"].value_counts(dropna=False).to_string())
    return result


# ---------------------------------------------------------------------------
# Step 5: Validation & Report
# ---------------------------------------------------------------------------
def validate_and_report(result, sources, crosswalk):
    """Flag issues and write build report."""
    lines = []
    lines.append("=" * 60)
    lines.append("UNIFIED SCHOOL COORDINATES — BUILD REPORT")
    lines.append("=" * 60)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Total counts
    total = len(result)
    with_coords = result["coord_source"].notna().sum()
    without_coords = result["coord_source"].isna().sum()
    lines.append(f"\nTotal schools in universe: {total:,}")
    lines.append(f"  With coordinates:    {with_coords:,}")
    lines.append(f"  Without coordinates: {without_coords:,}")

    # By coord_source
    lines.append(f"\nCoordinates by source:")
    for src, count in result["coord_source"].value_counts(dropna=False).items():
        label = src if src is not None else "(none)"
        lines.append(f"  {label}: {count:,}")

    # By location_source
    lines.append(f"\nLocation by source:")
    for src, count in result["location_source"].value_counts(dropna=False).items():
        label = src if src is not None else "(none)"
        lines.append(f"  {label}: {count:,}")

    # Crosswalk statistics
    lines.append(f"\nSchool ID Crosswalk:")
    lines.append(f"  Total entries: {len(crosswalk):,}")
    method_counts = crosswalk["match_method"].value_counts()
    for method, count in method_counts.items():
        lines.append(f"  {method}: {count:,}")
    non_identity = crosswalk[crosswalk["historical_id"] != crosswalk["canonical_id"]]
    lines.append(f"  Non-identity mappings (actual remaps): {len(non_identity):,}")

    # Cross-source discrepancies > 1 km
    lines.append(f"\nCross-source coordinate discrepancies (>1 km):")
    indexed = {}
    for label, df in sources.items():
        deduped = df.drop_duplicates(subset="school_id", keep="first")
        indexed[label] = deduped.set_index("school_id")[["latitude", "longitude"]]

    labels = list(indexed.keys())
    discrepancy_count = 0
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a_label, b_label = labels[i], labels[j]
            a, b = indexed[a_label], indexed[b_label]
            common = a.index.intersection(b.index)
            if len(common) == 0:
                continue
            ac, bc = a.loc[common], b.loc[common]
            dist = haversine_km(
                ac["latitude"].values, ac["longitude"].values,
                bc["latitude"].values, bc["longitude"].values,
            )
            n_over = int(np.sum(dist > 1.0))
            if n_over > 0:
                lines.append(
                    f"  {a_label} vs {b_label}: {n_over:,} schools >1 km apart"
                )
                discrepancy_count += n_over
    if discrepancy_count == 0:
        lines.append("  (none)")

    # Schools with no coords
    if without_coords > 0:
        lines.append(f"\nSchools with no coordinates ({without_coords:,}):")
        no_coord_df = result[result["coord_source"].isna()]
        sample = no_coord_df.head(20)
        for _, row in sample.iterrows():
            lines.append(f"  {row['school_id']}: {row.get('school_name', 'N/A')}")
        if without_coords > 20:
            lines.append(f"  ... and {without_coords - 20:,} more")

    report = "\n".join(lines)
    print(f"\n{report}")

    OUTPUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_REPORT_DIR / "build_public_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {report_path}")
    return report


# ---------------------------------------------------------------------------
# Step 6: Output
# ---------------------------------------------------------------------------
def write_output(result, crosswalk, report_text):
    """Write parquet, CSV, and Excel output."""
    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    coord_cols = [
        "school_id",
        "school_name",
        "latitude",
        "longitude",
        "coord_source",
        "monitoring_chosen_source",
        "sources_available",
        "region",
        "old_region",
        "province",
        "municipality",
        "barangay",
        "location_source",
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
        "psgc_validation",
        "urban_rural",
        "income_class",
    ]
    coords_df = result[coord_cols].sort_values("school_id").reset_index(drop=True)

    crosswalk_cols = [
        "historical_id",
        "canonical_id",
        "match_method",
        "year_first_seen",
        "year_last_seen",
    ]
    crosswalk_df = crosswalk[crosswalk_cols].sort_values(
        ["canonical_id", "historical_id"]
    ).reset_index(drop=True)

    # --- Parquet ---
    parquet_path = OUTPUT_DATA_DIR / "public_school_coordinates.parquet"
    coords_df.to_parquet(parquet_path, index=False)

    crosswalk_parquet = OUTPUT_DATA_DIR / "public_school_id_crosswalk.parquet"
    crosswalk_df.to_parquet(crosswalk_parquet, index=False)

    # --- CSV ---
    csv_path = OUTPUT_DATA_DIR / "public_school_coordinates.csv"
    coords_df.to_csv(csv_path, index=False)

    # --- Excel workbook (3 sheets) ---
    xlsx_path = OUTPUT_DATA_DIR / "public_school_coordinates.xlsx"

    # --- Compute summary stats for metadata ---
    psgc_match = (coords_df["psgc_validation"] == "psgc_match").sum()
    psgc_mismatch = (coords_df["psgc_validation"] == "psgc_mismatch").sum()
    psgc_no_val = (coords_df["psgc_validation"] == "psgc_no_validation").sum()
    active = (coords_df["enrollment_status"] == "active").sum()
    no_enroll = (coords_df["enrollment_status"] == "no_enrollment_reported").sum()

    metadata = pd.DataFrame([
        # --- Overview ---
        {"field": "Pipeline", "value": "Unified Public School Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Total Schools", "value": f"{len(coords_df):,}"},
        {"field": "With Coordinates", "value": f"{coords_df['coord_source'].notna().sum():,}"},
        {"field": "Without Coordinates", "value": f"{coords_df['coord_source'].isna().sum():,}"},
        {"field": "Crosswalk Entries", "value": f"{len(crosswalk_df):,}"},
        {"field": "", "value": ""},

        # --- Column Dictionary ---
        {"field": "COLUMN DICTIONARY", "value": ""},
        {"field": "school_id", "value": "Canonical (most recent) DepEd LIS School ID"},
        {"field": "school_name", "value": "Best available school name from highest-priority source"},
        {"field": "latitude", "value": "Final latitude (WGS84). Null if no coordinate source has data."},
        {"field": "longitude", "value": "Final longitude (WGS84). Null if no coordinate source has data."},
        {"field": "coord_source", "value": "Which source provided the coordinates (see Coordinate Sources below)"},
        {"field": "monitoring_chosen_source", "value": "If coord_source=monitoring_validated: which sub-source the validator chose (OSMapaaralan, NSBI, or New coordinates). Null otherwise."},
        {"field": "sources_available", "value": "Comma-separated list of all sources that had coordinates for this school. 'enrollment_only' if school is only known from enrollment data."},
        {"field": "region", "value": "DepEd administrative region (NIR-aware, from enrollment file)"},
        {"field": "old_region", "value": "DepEd region (pre-NIR naming; Negros Occidental in Region VI, Negros Oriental/Siquijor in Region VII)"},
        {"field": "province", "value": "Province (from best available source)"},
        {"field": "municipality", "value": "City or municipality (from best available source)"},
        {"field": "barangay", "value": "Barangay (from best available source)"},
        {"field": "location_source", "value": "Which source provided the admin location fields (see Location Sources below)"},
        {"field": "enrollment_status", "value": "Whether the school reported enrollment in SY 2024-2025 (see Enrollment Status below)"},
        {"field": "school_management", "value": "School management type (e.g., 'DepEd', 'Non-Sectarian', 'Sectarian', 'SUC', 'LUC'). From enrollment file."},
        {"field": "annex_status", "value": "Annex classification (e.g., 'Standalone School', 'Mother School', 'Annex/Extension School', 'Mobile School/Center'). From enrollment file."},
        {"field": "offers_es", "value": "Whether the school offers Elementary (True/False). From enrollment file."},
        {"field": "offers_jhs", "value": "Whether the school offers Junior High School (True/False). From enrollment file."},
        {"field": "offers_shs", "value": "Whether the school offers Senior High School (True/False). From enrollment file."},
        {"field": "shs_strand_offerings", "value": "Comma-delimited SHS strand offerings (e.g., 'ABM,HUMSS,STEM,TVL'). Derived from non-zero SHS enrollment by strand. Null if school does not offer SHS."},
        {"field": "psgc_region", "value": "10-digit PSA Philippine Standard Geographic Code for region"},
        {"field": "psgc_region_name", "value": "PSA official region name (e.g., 'Region I (Ilocos Region)')"},
        {"field": "psgc_province", "value": "10-digit PSGC for province"},
        {"field": "psgc_province_name", "value": "PSA official province name"},
        {"field": "psgc_municity", "value": "10-digit PSGC for municipality/city"},
        {"field": "psgc_municity_name", "value": "PSA official municipality/city name"},
        {"field": "psgc_barangay", "value": "10-digit PSGC for barangay (CLAIMED — from school-to-PSGC crosswalk, Q4 2024)"},
        {"field": "psgc_barangay_name", "value": "PSA official barangay name (claimed)"},
        {"field": "psgc_observed_barangay", "value": "10-digit PSGC for barangay (OBSERVED — from point-in-polygon against Q4 2025 shapefile). Which barangay the school's coordinates actually fall in."},
        {"field": "psgc_validation", "value": "Result of comparing claimed vs observed barangay (see PSGC Validation below)"},
        {"field": "urban_rural", "value": "Urban or Rural classification based on 2020 Census of Population and Housing"},
        {"field": "income_class", "value": "Municipal income classification (1st through 5th class) based on DOF D.O. 74, S. 2024"},
        {"field": "", "value": ""},

        # --- Coordinate Sources ---
        {"field": "COORDINATE SOURCES (coord_source values)", "value": ""},
        {"field": "  monitoring_validated", "value": "Priority 1. University-validated coordinates for schools flagged for coordinate mismatches."},
        {"field": "  osmapaaralan", "value": "Priority 2. Human-validated school footprints from OpenStreetMap (centroids of polygons)."},
        {"field": "  nsbi_2324", "value": "Priority 3. Official NSBI school list (SY 2023-2024). Dated but official."},
        {"field": "  geolocation_deped", "value": "Priority 4. Internal DepEd office revision of coordinates."},
        {"field": "  drrms_imrs", "value": "Priority 5. Self-reported via disaster incident reports (DRRMS IMRS 2025)."},
        {"field": "  (null)", "value": "No coordinate source has data for this school (enrollment-only)."},
        {"field": "", "value": ""},

        # --- Location Sources ---
        {"field": "LOCATION SOURCES (location_source values)", "value": ""},
        {"field": "  nsbi_2324", "value": "Priority 1. Most complete admin metadata."},
        {"field": "  geolocation_deped", "value": "Priority 2."},
        {"field": "  monitoring_validated", "value": "Priority 3."},
        {"field": "  osmapaaralan", "value": "Priority 4."},
        {"field": "  drrms_imrs", "value": "Priority 5."},
        {"field": "  enrollment", "value": "Fallback for enrollment-only schools."},
        {"field": "  (null)", "value": "No source has admin location data for this school."},
        {"field": "", "value": ""},

        # --- Enrollment Status ---
        {"field": "ENROLLMENT STATUS (enrollment_status values)", "value": ""},
        {"field": f"  active ({active:,} schools)", "value": "School has reported enrollment in SY 2024-2025."},
        {"field": f"  no_enrollment_reported ({no_enroll:,} schools)", "value": "School exists in coordinate sources but has no enrollment record. May have ceased operations, merged, or not yet reported."},
        {"field": "", "value": ""},

        # --- PSGC Validation ---
        {"field": "PSGC VALIDATION (psgc_validation values)", "value": ""},
        {"field": f"  psgc_match ({psgc_match:,} schools)", "value": "Coordinates fall within the claimed PSGC barangay polygon. Coordinates and admin assignment are consistent."},
        {"field": f"  psgc_mismatch ({psgc_mismatch:,} schools)", "value": "Coordinates fall in a DIFFERENT barangay than claimed. Possible causes: wrong coordinates, wrong admin assignment, or school near a barangay boundary."},
        {"field": f"  psgc_no_validation ({psgc_no_val:,} schools)", "value": "Cannot validate. School has no coordinates, no PSGC code, or coordinates fall outside all barangay polygons."},
        {"field": "", "value": ""},
        {"field": "PSGC NOTE", "value": "Claimed PSGC codes are from Q4 2024. Observed codes are from Q4 2025 shapefile. Some mismatches may be due to PSGC changes between quarters (barangay merges, splits, renames) rather than coordinate errors."},
        {"field": "", "value": ""},

        # --- Crosswalk ---
        {"field": "CROSSWALK MATCH METHODS (School ID Crosswalk sheet)", "value": ""},
        {"field": "  official_mapping", "value": "From DepEd's School ID Mapping tab. Authoritative."},
        {"field": "  spatial_name", "value": "Matched by spatial proximity (<100m) + name similarity (>=0.6). Heuristic."},
    ])

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        metadata.to_excel(writer, sheet_name="Metadata", index=False)
        coords_df.to_excel(writer, sheet_name="Public School Coordinates", index=False)
        crosswalk_df.to_excel(writer, sheet_name="School ID Crosswalk", index=False)

    print(f"\nOutput written:")
    print(f"  {parquet_path} ({len(coords_df):,} rows)")
    print(f"  {crosswalk_parquet} ({len(crosswalk_df):,} rows)")
    print(f"  {csv_path}")
    print(f"  {xlsx_path} (3 sheets)")
    return coords_df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def tag_enrollment_status(result, crosswalk):
    """Tag each school with enrollment status from enrollment files."""
    all_enrolled = set()
    for filepath in ENROLLMENT_FILES:
        if not filepath.exists():
            continue
        ids = load_enrollment.get_enrollment_ids(
            str(filepath), sector="public", crosswalk=crosswalk
        )
        all_enrolled.update(ids)

    result["enrollment_status"] = result["school_id"].apply(
        lambda x: "active" if x in all_enrolled else "no_enrollment_reported"
    )
    # Enrollment-only schools that ARE in enrollment are active
    # (they were added from enrollment, so they must be active)
    enroll_only = result["sources_available"] == "enrollment_only"
    result.loc[enroll_only, "enrollment_status"] = "active"

    active = (result["enrollment_status"] == "active").sum()
    no_enroll = (result["enrollment_status"] == "no_enrollment_reported").sum()
    print(f"\nEnrollment status:")
    print(f"  active: {active:,}")
    print(f"  no_enrollment_reported: {no_enroll:,}")
    return result


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

    # Drop the temporary psgc_school_name column (name is now in school_name)
    result = result.drop(columns=["psgc_school_name"], errors="ignore")

    print("\nSpatial validation (point-in-polygon)...")
    result = validate_psgc.spatial_lookup(root, result)
    result = validate_psgc.validate(result)

    return result


def enrich_from_enrollment(result):
    """Enrich schools with metadata from the enrollment file.

    Adds: school_name (backfill), region (NIR-aware), old_region,
    school_management, annex_status, offers_es/jhs/shs, shs_strand_offerings.
    """
    print("\nEnriching from enrollment metadata...")
    for filepath in ENROLLMENT_FILES:
        if not filepath.exists():
            continue
        meta = load_enrollment.load_full_metadata(str(filepath))
        print(f"  Enrollment metadata: {len(meta):,} schools")

        meta_indexed = meta.set_index("school_id")

        # Backfill school_name from enrollment where still blank
        blank_name = result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")
        in_meta = result["school_id"].isin(meta_indexed.index)
        backfill_name = blank_name & in_meta
        if backfill_name.sum() > 0:
            fill_ids = result.loc[backfill_name, "school_id"]
            result.loc[backfill_name, "school_name"] = meta_indexed.loc[
                fill_ids.values, "school_name"
            ].values
            print(f"  School names backfilled from enrollment: {backfill_name.sum():,}")

        # Add new columns from enrollment (join by school_id)
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
        # Current 'region' in result is from coordinate sources (old naming)
        # Rename it to old_region, then fill new region from enrollment
        if "old_region" not in result.columns:
            result["old_region"] = result["region"]

        # Fill region (NIR-aware) from enrollment
        result["region_new"] = None
        matched = result["school_id"].isin(meta_indexed.index)
        fill_ids = result.loc[matched, "school_id"]
        if len(fill_ids) > 0:
            result.loc[matched, "region_new"] = meta_indexed.loc[
                fill_ids.values, "region"
            ].values

        # For schools not in enrollment, derive region from old_region
        # (they're the same except for NIR provinces)
        no_new_region = result["region_new"].isna() | (result["region_new"] == "None")
        result.loc[no_new_region, "region_new"] = result.loc[no_new_region, "old_region"]

        # Also fill old_region from enrollment for schools that only have enrollment data
        no_old = result["old_region"].isna() | (result["old_region"] == "None")
        in_meta_old = no_old & result["school_id"].isin(meta_indexed.index)
        if in_meta_old.sum() > 0:
            fill_ids = result.loc[in_meta_old, "school_id"]
            result.loc[in_meta_old, "old_region"] = meta_indexed.loc[
                fill_ids.values, "old_region"
            ].values

        # Replace region with NIR-aware version
        result["region"] = result["region_new"]
        result = result.drop(columns=["region_new"])

        matched_count = matched.sum()
        print(f"  Enriched: {matched_count:,} / {len(result):,}")

    remaining_blank = (result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")).sum()
    print(f"  Remaining blank school names: {remaining_blank:,}")

    return result


def main():
    sources = load_all_sources()
    sources, crosswalk = build_and_apply_crosswalk(sources)
    universe = build_school_universe(sources, crosswalk)
    result = apply_coord_cascade(universe, sources)
    result = attach_location(result, sources)
    result = tag_enrollment_status(result, crosswalk)
    result = append_psgc(result)
    result = enrich_from_enrollment(result)
    report_text = validate_and_report(result, sources, crosswalk)
    write_output(result, crosswalk, report_text)
    print("\nDone.")


if __name__ == "__main__":
    main()
