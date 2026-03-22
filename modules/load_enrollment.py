"""Enrollment-based universe expansion, metadata enrichment, and enrollment status tagging.

Loads an enrollment CSV to:
1. Identify schools absent from coordinate sources (universe expansion)
2. Tag all schools with their enrollment status (active vs no reported enrollment)
3. Enrich school records with metadata (name, management, annex status,
   curricular offerings, SHS strands, region/old_region)

Designed to accept any school-level enrollment file with at minimum a
school_id and sector column. Supports both public and private sectors.
"""

import pandas as pd
import numpy as np
from .utils import normalize_school_id


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
        # Check both g11 and g12 columns for this strand
        for grade in ["g11", "g12"]:
            for sex in ["male", "female"]:
                col = f"{grade}_{prefix}_{sex}"
                val = row.get(col)
                if val is not None and str(val).strip() not in ("", "0", "nan", "None"):
                    try:
                        if int(float(val)) > 0:
                            strands.append(label)
                            break  # found enrollment in this strand, no need to check more columns
                    except (ValueError, TypeError):
                        pass
            else:
                continue
            break  # strand already added, move to next strand
    return ",".join(strands) if strands else None


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
        School records with columns: school_id, school_name, region, old_region,
        division, province, municipality, barangay, school_management,
        annex_status, offers_es, offers_jhs, offers_shs, shs_strand_offerings.
        Deduplicated by school_id.
    """
    df = pd.read_csv(filepath, dtype=str)

    if "school_id" not in df.columns:
        raise ValueError(
            f"Enrollment file must have a school_id column. "
            f"Found: {df.columns.tolist()}"
        )

    df["school_id"] = normalize_school_id(df["school_id"])
    df = df.dropna(subset=["school_id"])

    # Exclude PSO schools
    if "sector" in df.columns:
        df = df[df["sector"].str.strip().str.upper() != "PSO"].copy()

    # Filter by sector
    if "sector" in df.columns:
        df = df[df["sector"].str.strip().str.lower() == sector.lower()].copy()

    df = df.drop_duplicates(subset="school_id", keep="first")

    # Derive old_region (pre-NIR) from region + province
    if "region" in df.columns:
        df["old_region"] = df.apply(_derive_old_region, axis=1)

    # Derive SHS strand offerings
    shs_cols_exist = any(c for c in df.columns if c.startswith("g11_") or c.startswith("g12_"))
    if shs_cols_exist and "offers_shs" in df.columns:
        shs_mask = df["offers_shs"].str.strip().str.lower() == "true"
        df["shs_strand_offerings"] = None
        df.loc[shs_mask, "shs_strand_offerings"] = df.loc[shs_mask].apply(
            _derive_shs_strands, axis=1
        )
    else:
        df["shs_strand_offerings"] = None

    # Normalize boolean offering columns to True/False strings
    for col in ["offers_es", "offers_jhs", "offers_shs"]:
        if col in df.columns:
            df[col] = df[col].str.strip().str.lower().map(
                {"true": "True", "false": "False"}
            )

    # Build output columns
    out_cols = ["school_id"]
    for col in [
        "school_name", "region", "old_region", "division", "province",
        "municipality", "barangay", "school_management", "annex_status",
        "offers_es", "offers_jhs", "offers_shs", "shs_strand_offerings",
    ]:
        if col not in df.columns:
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


def load_full_metadata(filepath):
    """Load the full enrollment file for metadata enrichment (all sectors).

    Returns a lookup keyed by school_id with all metadata columns.
    Used by the orchestrator to enrich the final output after the
    coordinate cascade.

    Parameters
    ----------
    filepath : str
        Path to a CSV enrollment file.

    Returns
    -------
    pd.DataFrame
        All schools (excluding PSO) with metadata columns.
    """
    df = pd.read_csv(filepath, dtype=str)

    if "school_id" not in df.columns:
        raise ValueError(f"Enrollment file must have a school_id column.")

    df["school_id"] = normalize_school_id(df["school_id"])
    df = df.dropna(subset=["school_id"])

    # Exclude PSO
    if "sector" in df.columns:
        df = df[df["sector"].str.strip().str.upper() != "PSO"].copy()

    df = df.drop_duplicates(subset="school_id", keep="first")

    # Derive old_region
    if "region" in df.columns:
        df["old_region"] = df.apply(_derive_old_region, axis=1)

    # Derive SHS strands
    shs_cols_exist = any(c for c in df.columns if c.startswith("g11_") or c.startswith("g12_"))
    if shs_cols_exist and "offers_shs" in df.columns:
        shs_mask = df["offers_shs"].str.strip().str.lower() == "true"
        df["shs_strand_offerings"] = None
        df.loc[shs_mask, "shs_strand_offerings"] = df.loc[shs_mask].apply(
            _derive_shs_strands, axis=1
        )
    else:
        df["shs_strand_offerings"] = None

    # Normalize booleans
    for col in ["offers_es", "offers_jhs", "offers_shs"]:
        if col in df.columns:
            df[col] = df[col].str.strip().str.lower().map(
                {"true": "True", "false": "False"}
            )

    out_cols = [
        "school_id", "school_name", "region", "old_region", "division",
        "province", "municipality", "barangay", "school_management",
        "annex_status", "offers_es", "offers_jhs", "offers_shs",
        "shs_strand_offerings",
    ]
    for col in out_cols:
        if col not in df.columns:
            df[col] = None

    return df[out_cols].reset_index(drop=True)
