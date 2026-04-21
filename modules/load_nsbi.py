"""Source C: SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.

Official school list from DepEd's National School Building Inventory (NSBI)
system. Sheet 'DB', header at row index 5. Has the most complete
administrative metadata (region, division, province, municipality, barangay).
"""

from pathlib import Path

import pandas as pd

from .utils import SOURCE_NSBI, fix_swapped_coords, has_valid_coords, normalize_school_id, reject_out_of_ph_bounds

RAW_PATH = "data/bronze/live/SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.xlsx"
SILVER_PATH = "data/silver/nsbi.parquet"


def preprocess(project_root):
    """Read bronze Excel, normalize, write silver parquet. Returns the silver DataFrame."""
    df = pd.read_excel(
        f"{project_root}/{RAW_PATH}",
        sheet_name="DB",
        header=5,
        dtype=str,
    )

    renamed = df.rename(columns={
        "LIS SCHOOL ID": "school_id",
        "School Name": "school_name",
        "Region": "region",
        "Division": "division",
        "Province": "province",
        "Municipality": "municipality",
        "Barangay": "barangay",
        "Longitude": "longitude",
        "Latitude": "latitude",
    })

    renamed["school_id"] = normalize_school_id(renamed["school_id"])
    renamed["latitude"] = pd.to_numeric(renamed["latitude"], errors="coerce")
    renamed["longitude"] = pd.to_numeric(renamed["longitude"], errors="coerce")
    renamed, _ = fix_swapped_coords(renamed, source_label=SOURCE_NSBI)
    renamed, _ = reject_out_of_ph_bounds(renamed, source_label=SOURCE_NSBI)
    renamed = renamed[has_valid_coords(renamed)].copy()
    renamed["source"] = SOURCE_NSBI

    out_cols = [
        "school_id", "school_name", "latitude", "longitude",
        "region", "division", "province", "municipality", "barangay",
        "source", "_was_swapped",
    ]
    out = renamed[out_cols].reset_index(drop=True)

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
