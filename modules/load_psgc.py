"""PSGC crosswalk loader.

Loads the SY 2024-2025 School Level Database WITH PSGC, which maps
DepEd school IDs to PSA's Philippine Standard Geographic Codes.

Handles Excel's leading-zero stripping by left-padding all PSGC codes
to 10 digits.
"""

import pandas as pd
from .utils import normalize_school_id

RAW_PATH = "data/raw/SY 2024-2025 School Level Database WITH PSGC.xlsx"
PSGC_CODE_LENGTH = 10


def _pad_psgc(series):
    """Left-pad PSGC codes to 10 digits (Excel strips leading zeros)."""
    return series.astype(str).str.strip().str.zfill(PSGC_CODE_LENGTH).where(
        series.notna(), None
    )


def load(project_root):
    """Load the PSGC crosswalk.

    Parameters
    ----------
    project_root : str
        Project root directory.

    Returns
    -------
    pd.DataFrame
        Columns: school_id, psgc_region, psgc_region_name, psgc_province,
        psgc_province_name, psgc_municity, psgc_municity_name,
        psgc_barangay, psgc_barangay_name, urban_rural, income_class.
        One row per school, keyed by school_id.
    """
    df = pd.read_excel(
        f"{project_root}/{RAW_PATH}",
        sheet_name="DB",
        header=6,
        dtype=str,
    )

    renamed = df.rename(columns={
        "BEIS School ID": "school_id",
        "(PSGC) REGION": "psgc_region",
        "(PSGC) REGION NAME": "psgc_region_name",
        "(PSGC) PROVINCE": "psgc_province",
        "(PSGC) PROVINCE NAME": "psgc_province_name",
        "(PSGC) MUNCIPAL/CITY": "psgc_municity",
        "(PSGC) MUNCIPAL/CITY NAME": "psgc_municity_name",
        "(PSGC) BARANGAY": "psgc_barangay",
        "(PSGC) BARANGAY NAME": "psgc_barangay_name",
    })

    # Resolve the income class column (has embedded newline in header)
    income_cols = [c for c in renamed.columns if "INCOME" in c.upper() and ".1" not in c]
    if income_cols:
        renamed = renamed.rename(columns={income_cols[0]: "income_class"})

    # Resolve urban/rural column (has embedded newline in header)
    ur_cols = [c for c in renamed.columns if "Urban" in c or "Rural" in c]
    if ur_cols:
        renamed = renamed.rename(columns={ur_cols[0]: "urban_rural"})

    renamed["school_id"] = normalize_school_id(renamed["school_id"])
    renamed = renamed.dropna(subset=["school_id"])

    # Left-pad PSGC codes to 10 digits
    for col in ["psgc_region", "psgc_province", "psgc_municity", "psgc_barangay"]:
        renamed[col] = _pad_psgc(renamed[col])

    # Clean income class (normalize "1St" → "1st", etc.)
    if "income_class" in renamed.columns:
        renamed["income_class"] = renamed["income_class"].str.strip().str.lower().str.capitalize()

    renamed = renamed.drop_duplicates(subset="school_id", keep="first")

    out_cols = [
        "school_id",
        "psgc_region", "psgc_region_name",
        "psgc_province", "psgc_province_name",
        "psgc_municity", "psgc_municity_name",
        "psgc_barangay", "psgc_barangay_name",
        "urban_rural", "income_class",
    ]
    # Only include columns that exist
    out_cols = [c for c in out_cols if c in renamed.columns]
    return renamed[out_cols].reset_index(drop=True)
