"""Preprocessor for the School ID Mapping sheet of the Geolocation Excel.

The bronze file Geolocation of Public Schools_DepEd.xlsx contains two
semantically-independent datasets:

  - Geolocations sheet   → priority 4 coord source (handled by load_geolocation)
  - School ID Mapping    → historical-to-canonical ID transitions used by
                            build_crosswalk.py Layer 1 (handled here)

Splitting into two silver artifacts (geolocation.parquet + sos_mapping.parquet)
keeps the two concerns separate and lets downstream consumers use either
independently.
"""

from pathlib import Path

import pandas as pd

RAW_PATH = "data/bronze/frozen/Geolocation of Public Schools_DepEd.xlsx"
SHEET_NAME = "School ID Mapping"
SILVER_PATH = "data/silver/sos_mapping.parquet"


def preprocess(project_root):
    """Read the School ID Mapping sheet, coerce to string dtypes, write silver.

    Silver preserves the original column set as-is (same columns the crosswalk
    Layer 1 builder iterates over: old_school_id, BEIS School ID, sy_2005..sy_2024,
    school_id_2024, school_name etc.). No row filtering, no derivation — that
    work stays in build_crosswalk.py.

    Returns the silver DataFrame.
    """
    df = pd.read_excel(
        f"{project_root}/{RAW_PATH}",
        sheet_name=SHEET_NAME,
        header=0,
        dtype=str,
    )

    silver_path = Path(project_root) / SILVER_PATH
    silver_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(silver_path, index=False)
    print(f"  Silver written: {silver_path}  ({len(df):,} rows)")
    return df


def read_silver(project_root):
    """Read the materialized silver parquet."""
    path = Path(project_root) / SILVER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Silver not found: {path}. Run preprocess first.")
    return pd.read_parquet(path)
