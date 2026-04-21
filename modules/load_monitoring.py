"""Source A: DepEd Data Encoding Monitoring Sheet (sheets 1-5).

University-validated coordinates for ~11,331 schools flagged for coordinate
mismatches. Returns only rows with Findings == 'Validated' and non-null
validated coordinates (~8,570 schools).

Medallion layers:
  - preprocess(): reads the bronze Excel, normalizes, writes silver parquet
  - read_silver(): reads the silver parquet for consumption by the cascade
"""

from pathlib import Path

import pandas as pd

from .utils import SOURCE_MONITORING, fix_swapped_coords, has_valid_coords, normalize_school_id, reject_out_of_ph_bounds

RAW_PATH = "data/bronze/frozen/02. DepEd Data Encoding Monitoring Sheet.xlsx"
SILVER_PATH = "data/silver/monitoring.parquet"
SHEETS = ["1", "2", "3", "4", "5"]

# Column mapping from raw header (row index 1) to normalized names.
# Headers contain newlines (e.g., "Validated\nLongitude"), so we map by position.
# Positions are consistent across all 5 sheets:
#   0: Assigned, 1: #, 2: Batch, 3: Region, 4: Division,
#   5: LIS School ID, 6: School Name, 7: Barangay,
#   8: NSBI Longitude, 9: NSBI Latitude,
#   10: OSM Longitude, 11: OSM Latitude,
#   12: Comparison Longitude, 13: Comparison Latitude,
#   14: Findings, 15: Source,
#   16: Validated Longitude, 17: Validated Latitude,
#   18+: Remarks columns (vary by sheet)


def preprocess(project_root):
    """Read bronze, normalize, write silver parquet. Returns the silver DataFrame."""
    frames = []
    for sheet in SHEETS:
        df = pd.read_excel(
            f"{project_root}/{RAW_PATH}",
            sheet_name=sheet,
            header=1,
            dtype=str,
        )
        frames.append(df)

    raw = pd.concat(frames, ignore_index=True)

    # Normalize column access by position-based rename of the columns we need.
    # Use iloc-based extraction since header names may have embedded newlines.
    cols = raw.columns.tolist()
    renamed = raw.rename(columns={
        cols[3]: "region",
        cols[4]: "division",
        cols[5]: "school_id",
        cols[6]: "school_name",
        cols[7]: "barangay",
        cols[14]: "findings",
        cols[15]: "monitoring_chosen_source",
        cols[16]: "validated_longitude",
        cols[17]: "validated_latitude",
    })

    # Filter to validated rows with coordinates
    validated = renamed[renamed["findings"].str.strip().str.lower() == "validated"].copy()
    validated["latitude"] = pd.to_numeric(validated["validated_latitude"], errors="coerce")
    validated["longitude"] = pd.to_numeric(validated["validated_longitude"], errors="coerce")
    validated, _ = fix_swapped_coords(validated, source_label=SOURCE_MONITORING)
    validated, _ = reject_out_of_ph_bounds(validated, source_label=SOURCE_MONITORING)
    validated = validated[has_valid_coords(validated)].copy()

    # Normalize
    validated["school_id"] = normalize_school_id(validated["school_id"])
    validated["source"] = SOURCE_MONITORING

    # Clean up monitoring_chosen_source
    validated["monitoring_chosen_source"] = (
        validated["monitoring_chosen_source"].str.strip().fillna("")
    )

    out_cols = [
        "school_id", "school_name", "latitude", "longitude",
        "region", "division", "barangay",
        "monitoring_chosen_source", "source", "_was_swapped",
    ]
    out = validated[out_cols].reset_index(drop=True)

    silver_path = Path(project_root) / SILVER_PATH
    silver_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(silver_path, index=False)
    print(f"  Silver written: {silver_path}  ({len(out):,} rows)")
    return out


def read_silver(project_root):
    """Read the materialized silver parquet."""
    path = Path(project_root) / SILVER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Silver not found: {path}. Run preprocess first.")
    return pd.read_parquet(path)
