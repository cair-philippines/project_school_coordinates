"""Data loader — reads parquet files into memory as plain dicts."""

import math
from pathlib import Path
import pandas as pd

# Location columns to normalize for consistent casing across sources
LOCATION_COLS = ["region", "province", "municipality", "barangay"]


def _title_case(val):
    """Normalize location strings to title case for display consistency."""
    import re
    if not val or not isinstance(val, str):
        return val
    val = val.strip()
    if not val:
        return None
    # Normalize whitespace: collapse multiple spaces, fix comma spacing
    val = re.sub(r'\s+', ' ', val)
    val = re.sub(r'\s*,\s*', ', ', val)
    # Preserve known all-caps abbreviations
    KEEP_UPPER = {"NCR", "CAR", "BARMM", "NIR", "CARAGA", "MIMAROPA"}
    if val.upper() in KEEP_UPPER:
        return val.upper()
    # Preserve "Region X" format
    if val.upper().startswith("REGION "):
        return "Region " + val[7:].strip()
    return val.title()


def _clean_row(row: dict) -> dict:
    """Replace NaN/None with None for JSON serialization."""
    cleaned = {}
    for k, v in row.items():
        if isinstance(v, float) and math.isnan(v):
            cleaned[k] = None
        else:
            cleaned[k] = v
    return cleaned


def _normalize_locations(df):
    """Normalize location column casing for consistency across datasets."""
    for col in LOCATION_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_title_case)
    return df


def load_all(data_dir: Path) -> list[dict]:
    """Load public and private school datasets, return combined list of dicts."""
    schools = []

    # Public schools
    public_path = data_dir / "public_school_coordinates.parquet"
    if public_path.exists():
        df = pd.read_parquet(public_path)
        df["sector"] = "public"
        df = _normalize_locations(df)
        for _, row in df.iterrows():
            schools.append(_clean_row(row.to_dict()))
        print(f"  Public: {len(df):,} schools")

    # Private schools
    private_path = data_dir / "private_school_coordinates.parquet"
    if private_path.exists():
        df = pd.read_parquet(private_path)
        df["sector"] = "private"
        df = _normalize_locations(df)
        # Map coord_status to coord_source-like field for display
        df["coord_source"] = df["coord_status"].apply(
            lambda x: "tosf_self_reported" if x in ("valid", "fixed_swap") else None
        )
        for _, row in df.iterrows():
            schools.append(_clean_row(row.to_dict()))
        print(f"  Private: {len(df):,} schools")

    return schools


def build_filter_options(schools: list[dict]) -> dict:
    """Pre-compute distinct filter values."""
    return {
        "sectors": sorted(set(s["sector"] for s in schools)),
        "regions": sorted(set(s["region"] for s in schools if s.get("region"))),
    }
