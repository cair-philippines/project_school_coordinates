"""Enrollment preprocessing, universe expansion, and metadata enrichment.

Medallion layers:
  - preprocess(): reads the bronze enrollment CSV, normalizes, writes silver.
    Silver preserves ALL sectors except PSO (PSO is excluded at preprocess).
  - read_silver(sector=None): reads the silver parquet, optionally filtering.
  - find_missing(): identifies enrollment schools absent from a universe.
  - get_enrollment_ids(): set of enrolled IDs after crosswalk remap.

Designed to accept any school-level enrollment file with at minimum a
school_id and sector column. Supports both public and private sectors.
"""

from pathlib import Path

import pandas as pd
import numpy as np

from .utils import normalize_school_id

RAW_PATH = "data/bronze/live/project_bukas_enrollment_2024-25.csv"
SILVER_PATH = "data/silver/enrollment.parquet"


# NIR province mapping: province → old region (pre-NIR)
NIR_PROVINCES = {
    "negros occidental": "Region VI",
    "negros oriental": "Region VII",
    "siquijor": "Region VII",
}

# SHS strand column prefixes (g11 and g12)
SHS_STRAND_PREFIXES = [
    ("abm", "ABM"),
    ("arts", "Arts and Design"),
    ("gas", "GAS"),
    ("humss", "HUMSS"),
    ("maritime", "Maritime"),
    ("sports", "Sports"),
    ("stem", "STEM"),
    ("tvl", "TVL"),
    ("unique", "Unique"),
]


def _derive_old_region(row):
    """Derive old_region from region + province for NIR schools."""
    region = row.get("region")
    province = row.get("province")
    if region and str(region).strip().upper() == "NIR" and province:
        return NIR_PROVINCES.get(str(province).strip().lower(), region)
    return region


def _derive_shs_strands(row):
    """Build comma-delimited SHS strand offerings from enrollment columns."""
    strands = []
    for prefix, label in SHS_STRAND_PREFIXES:
        for grade in ["g11", "g12"]:
            for sex in ["male", "female"]:
                col = f"{grade}_{prefix}_{sex}"
                val = row.get(col)
                if val is not None and str(val).strip() not in ("", "0", "nan", "None"):
                    try:
                        if int(float(val)) > 0:
                            strands.append(label)
                            break
                    except (ValueError, TypeError):
                        pass
            else:
                continue
            break
    return ",".join(strands) if strands else None


def preprocess(project_root, filepath=None):
    """Read bronze enrollment CSV, normalize, write silver parquet.

    Silver contains ALL sectors present in bronze except PSO, with derived
    SHS strands and old_region. The sector column is preserved so downstream
    callers can filter.

    Parameters
    ----------
    project_root : str
        Project root directory.
    filepath : str or Path, optional
        Override for the bronze path. Defaults to RAW_PATH.

    Returns
    -------
    pd.DataFrame
        The silver DataFrame (also written to disk).
    """
    src = Path(filepath) if filepath else Path(project_root) / RAW_PATH
    df = pd.read_csv(src, dtype=str)

    if "school_id" not in df.columns:
        raise ValueError(
            f"Enrollment file must have a school_id column. "
            f"Found: {df.columns.tolist()}"
        )

    df["school_id"] = normalize_school_id(df["school_id"])
    df = df.dropna(subset=["school_id"])

    # Silver preserves ALL sectors (including PSO). Downstream filtering
    # happens in read_silver(sector=...) and load_full_metadata().
    df = df.drop_duplicates(subset="school_id", keep="first")

    if "region" in df.columns:
        df["old_region"] = df.apply(_derive_old_region, axis=1)

    shs_cols_exist = any(c for c in df.columns if c.startswith("g11_") or c.startswith("g12_"))
    if shs_cols_exist and "offers_shs" in df.columns:
        shs_mask = df["offers_shs"].str.strip().str.lower() == "true"
        df["shs_strand_offerings"] = None
        df.loc[shs_mask, "shs_strand_offerings"] = df.loc[shs_mask].apply(
            _derive_shs_strands, axis=1
        )
    else:
        df["shs_strand_offerings"] = None

    for col in ["offers_es", "offers_jhs", "offers_shs"]:
        if col in df.columns:
            df[col] = df[col].str.strip().str.lower().map(
                {"true": "True", "false": "False"}
            )

    out_cols = [
        "school_id", "sector", "school_name", "region", "old_region", "division",
        "province", "municipality", "barangay", "school_management", "annex_status",
        "offers_es", "offers_jhs", "offers_shs", "shs_strand_offerings",
    ]
    for col in out_cols:
        if col not in df.columns:
            df[col] = None

    out = df[out_cols].reset_index(drop=True)

    silver_path = Path(project_root) / SILVER_PATH
    silver_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(silver_path, index=False)
    print(f"  Silver written: {silver_path}  ({len(out):,} rows)")
    return out


def read_silver(project_root, sector=None):
    """Read the materialized silver parquet, optionally filtered by sector.

    Silver contains ALL sectors including PSO; callers opt into filtering.
    """
    path = Path(project_root) / SILVER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Silver not found: {path}. Run preprocess first.")
    df = pd.read_parquet(path)
    if sector:
        df = df[df["sector"].str.strip().str.lower() == sector.lower()]
    return df.reset_index(drop=True)


def find_missing(enrollment_df, universe_ids, crosswalk=None):
    """Identify enrollment schools not present in the coordinate universe."""
    df = enrollment_df.copy()

    if crosswalk is not None:
        from .build_crosswalk import remap_source
        df, _, _ = remap_source(df, crosswalk)

    missing_mask = ~df["school_id"].isin(universe_ids)
    missing = df[missing_mask].drop_duplicates(subset="school_id", keep="first")
    return missing.reset_index(drop=True)


def get_enrollment_ids(project_root, sector="public", crosswalk=None):
    """Return the set of school IDs with reported enrollment for a sector."""
    df = read_silver(project_root, sector=sector)

    if crosswalk is not None:
        from .build_crosswalk import remap_source
        df, _, _ = remap_source(df, crosswalk)

    return set(df["school_id"].dropna())


def load_full_metadata(project_root):
    """Read the enrollment silver for metadata enrichment.

    Excludes PSO (preserves historical pre-medallion behavior — enrichment
    should never apply PSO metadata to public/private universe schools).
    """
    df = read_silver(project_root)
    if "sector" in df.columns:
        df = df[df["sector"].str.strip().str.upper() != "PSO"]
    return df.reset_index(drop=True)
