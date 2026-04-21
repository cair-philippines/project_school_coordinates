"""Source E: DRRMS IMRS (Incident Management Reporting System) 2025.

Self-reported school coordinates from disaster/emergency reports submitted
by school officials to DepEd's Disaster Risk Reduction Management Service.

Each row is a disaster report — multiple reports per school are common.
Deduplicated to one row per school, keeping the first report's coordinates.
"""

import pandas as pd
import re
from .utils import SOURCE_DRRMS, fix_swapped_coords, has_valid_coords, normalize_school_id, reject_out_of_ph_bounds

RAW_PATH = "data/bronze/live/DRRMS IMRS data 2025.csv"

# Normalize long region names to short format used by other sources
REGION_MAP = {
    "region i (ilocos region)": "Region I",
    "region ii (cagayan valley)": "Region II",
    "region iii (central luzon)": "Region III",
    "region iv-a (calabarzon)": "Region IV-A",
    "mimaropa region": "MIMAROPA",
    "region v (bicol region)": "Region V",
    "region vi (western visayas)": "Region VI",
    "region vii (central visayas)": "Region VII",
    "region viii (eastern visayas)": "Region VIII",
    "region ix (zamboanga)": "Region IX",
    "region x (northern mindanao)": "Region X",
    "region xi (davao)": "Region XI",
    "region xii (soccsksargen)": "Region XII",
    "national capital region (ncr)": "NCR",
    "cordillera administrative region (car)": "CAR",
    "caraga": "CARAGA",
    "bangsamoro autonomous region in muslim mindanao (barmm)": "BARMM",
    "negros island region (nir)": "NIR",
}


def _normalize_region(val):
    """Map long DRRMS region names to the short format used by other sources."""
    if not val or not isinstance(val, str):
        return None
    key = val.strip().lower()
    return REGION_MAP.get(key, val.strip())


def load(project_root):
    """Load and normalize DRRMS IMRS data.

    Parameters
    ----------
    project_root : str or Path
        Root directory of the project.

    Returns
    -------
    pd.DataFrame
        Normalized DataFrame with columns: school_id, school_name, latitude,
        longitude, region, division, province, municipality, barangay, source.
        Deduplicated to one row per school.
    """
    df = pd.read_csv(
        f"{project_root}/{RAW_PATH}",
        dtype=str,
    )

    renamed = df.rename(columns={
        "deped school id number": "school_id",
        "name of school or deped facility": "school_name",
        "region": "region",
        "province": "province",
        "municipality/city": "municipality",
        "barangay": "barangay",
        "latitude": "latitude",
        "longitude": "longitude",
        "sdo": "division",
    })

    renamed["school_id"] = normalize_school_id(renamed["school_id"])
    renamed = renamed.dropna(subset=["school_id"])

    # Deduplicate: one row per school (keep first disaster report)
    renamed = renamed.drop_duplicates(subset="school_id", keep="first").copy()

    # Parse coordinates
    renamed["latitude"] = pd.to_numeric(renamed["latitude"], errors="coerce")
    renamed["longitude"] = pd.to_numeric(renamed["longitude"], errors="coerce")
    renamed, _ = fix_swapped_coords(renamed, source_label=SOURCE_DRRMS)
    renamed, _ = reject_out_of_ph_bounds(renamed, source_label=SOURCE_DRRMS)
    renamed = renamed[has_valid_coords(renamed)].copy()

    # Normalize region names
    renamed["region"] = renamed["region"].apply(_normalize_region)

    # Normalize province/municipality to title case for consistency
    for col in ["province", "municipality", "barangay"]:
        renamed[col] = renamed[col].str.strip().str.title() if col in renamed.columns else None

    renamed["source"] = SOURCE_DRRMS

    out_cols = [
        "school_id", "school_name", "latitude", "longitude",
        "region", "division", "province", "municipality", "barangay",
        "source", "_was_swapped",
    ]
    return renamed[out_cols].reset_index(drop=True)
