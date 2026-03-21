"""Enrollment-based universe expansion and enrollment status tagging.

Loads an enrollment CSV to:
1. Identify schools absent from coordinate sources (universe expansion)
2. Tag all schools with their enrollment status (active vs no reported enrollment)

Designed to accept any school-level enrollment file with at minimum a
school_id and sector column. Supports both public and private sectors.
"""

import pandas as pd
from .utils import normalize_school_id


# Column mapping: known enrollment file variants → normalized names.
# Keys are lowercased raw column names.
COLUMN_ALIASES = {
    "school_id": "school_id",
    "schoolid": "school_id",
    "lis school id": "school_id",
    "lis_school_id": "school_id",
    "beis school id": "school_id",
    "sector": "sector",
    "old_region": "region",
    "region": "region",
    "division": "division",
    "province": "province",
    "municipality": "municipality",
    "barangay": "barangay",
}


def _resolve_columns(df):
    """Map raw columns to normalized names using COLUMN_ALIASES."""
    rename_map = {}
    raw_lower = {c: c.lower().strip() for c in df.columns}
    for raw_col, lower_col in raw_lower.items():
        if lower_col in COLUMN_ALIASES:
            rename_map[raw_col] = COLUMN_ALIASES[lower_col]
    return df.rename(columns=rename_map)


def load(filepath, sector="public"):
    """Load an enrollment file and return school records for a given sector.

    Parameters
    ----------
    filepath : str
        Path to a CSV enrollment file.
    sector : str
        Sector to filter: "public" or "private". Default "public".

    Returns
    -------
    pd.DataFrame
        School records with columns: school_id, region, division,
        province, municipality, barangay. Deduplicated by school_id.
    """
    df = pd.read_csv(filepath, dtype=str)
    df = _resolve_columns(df)

    if "school_id" not in df.columns:
        raise ValueError(
            f"Enrollment file must have a school_id column. "
            f"Found: {df.columns.tolist()}"
        )

    df["school_id"] = normalize_school_id(df["school_id"])
    df = df.dropna(subset=["school_id"])

    # Filter by sector
    if "sector" in df.columns:
        df = df[df["sector"].str.strip().str.lower() == sector.lower()].copy()

    df = df.drop_duplicates(subset="school_id", keep="first")

    # Return available location columns
    out_cols = ["school_id"]
    for col in ["region", "division", "province", "municipality", "barangay"]:
        if col in df.columns:
            out_cols.append(col)
        else:
            df[col] = None
            out_cols.append(col)

    return df[out_cols].reset_index(drop=True)


def find_missing(enrollment_df, universe_ids, crosswalk=None):
    """Identify enrollment schools not present in the coordinate universe.

    Parameters
    ----------
    enrollment_df : pd.DataFrame
        Output of load().
    universe_ids : set
        Set of canonical school IDs already in the universe.
    crosswalk : pd.DataFrame, optional
        Crosswalk table. If provided, enrollment IDs are first resolved
        through the crosswalk before checking against the universe.

    Returns
    -------
    pd.DataFrame
        Enrollment schools not found in the universe (after crosswalk
        resolution), with their admin metadata.
    """
    df = enrollment_df.copy()

    # Remap through crosswalk if available
    if crosswalk is not None:
        from .build_crosswalk import remap_source
        df, _ = remap_source(df, crosswalk)

    # Find IDs still not in the universe
    missing_mask = ~df["school_id"].isin(universe_ids)
    missing = df[missing_mask].drop_duplicates(subset="school_id", keep="first")

    return missing.reset_index(drop=True)


def get_enrollment_ids(filepath, sector="public", crosswalk=None):
    """Get the set of school IDs with reported enrollment for a sector.

    Parameters
    ----------
    filepath : str
        Path to a CSV enrollment file.
    sector : str
        Sector to filter: "public" or "private".
    crosswalk : pd.DataFrame, optional
        If provided, enrollment IDs are remapped to canonical IDs.

    Returns
    -------
    set
        School IDs with reported enrollment.
    """
    df = load(filepath, sector=sector)

    if crosswalk is not None:
        from .build_crosswalk import remap_source
        df, _ = remap_source(df, crosswalk)

    return set(df["school_id"].dropna())
