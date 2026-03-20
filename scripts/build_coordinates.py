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
from modules import load_monitoring, load_nsbi, load_geolocation, load_osmapaaralan
from modules import build_crosswalk
from modules.utils import (
    COORD_PRIORITY,
    LOCATION_PRIORITY,
    SOURCE_MONITORING,
    haversine_km,
)

OUTPUT_DATA_DIR = PROJECT_ROOT / "data" / "modified"
OUTPUT_REPORT_DIR = PROJECT_ROOT / "output"


# ---------------------------------------------------------------------------
# Step 1: Load all sources
# ---------------------------------------------------------------------------
def load_all_sources():
    """Load and return a dict of source label -> DataFrame."""
    print("Loading sources...")
    root = str(PROJECT_ROOT)
    sources = {
        "monitoring_validated": load_monitoring.load(root),
        "osmapaaralan": load_osmapaaralan.load(root),
        "nsbi_2324": load_nsbi.load(root),
        "geolocation_deped": load_geolocation.load(root),
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
    return remapped_sources, crosswalk


# ---------------------------------------------------------------------------
# Step 2: Establish the school universe
# ---------------------------------------------------------------------------
def build_school_universe(sources):
    """Union all school_ids across sources into a master DataFrame."""
    all_ids = pd.concat(
        [df[["school_id"]].drop_duplicates() for df in sources.values()],
        ignore_index=True,
    ).drop_duplicates(subset="school_id")
    print(f"\nSchool universe: {len(all_ids):,} unique canonical school IDs")
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
        "province",
        "municipality",
        "barangay",
        "location_source",
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

    metadata = pd.DataFrame([
        {"field": "Pipeline", "value": "Public School Coordinates"},
        {"field": "Generated", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"field": "Total Schools", "value": str(len(coords_df))},
        {"field": "With Coordinates", "value": str(coords_df["coord_source"].notna().sum())},
        {"field": "Without Coordinates", "value": str(coords_df["coord_source"].isna().sum())},
        {"field": "Crosswalk Entries", "value": str(len(crosswalk_df))},
        {"field": "", "value": ""},
        {"field": "Source Priority (Coordinates)", "value": ""},
        {"field": "  1 (highest)", "value": "monitoring_validated — University-validated coordinates"},
        {"field": "  2", "value": "osmapaaralan — OSM human-validated school footprints"},
        {"field": "  3", "value": "nsbi_2324 — Official NSBI school list (SY 2023-2024)"},
        {"field": "  4 (lowest)", "value": "geolocation_deped — Internal DepEd office revision"},
        {"field": "", "value": ""},
        {"field": "Source Priority (Location Columns)", "value": ""},
        {"field": "  1 (highest)", "value": "nsbi_2324"},
        {"field": "  2", "value": "geolocation_deped"},
        {"field": "  3", "value": "monitoring_validated"},
        {"field": "  4 (lowest)", "value": "osmapaaralan"},
        {"field": "", "value": ""},
        {"field": "Crosswalk Match Methods", "value": ""},
        {"field": "  official_mapping", "value": "From School ID Mapping tab (authoritative)"},
        {"field": "  spatial_name", "value": "Spatial proximity (<100m) + name similarity (>=0.6)"},
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
def main():
    sources = load_all_sources()
    sources, crosswalk = build_and_apply_crosswalk(sources)
    universe = build_school_universe(sources)
    result = apply_coord_cascade(universe, sources)
    result = attach_location(result, sources)
    report_text = validate_and_report(result, sources, crosswalk)
    write_output(result, crosswalk, report_text)
    print("\nDone.")


if __name__ == "__main__":
    main()
