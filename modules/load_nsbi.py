"""Source C: SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.

Official school list from DepEd's National School Building Inventory (NSBI)
system. Sheet 'DB', header at row index 5. Has the most complete
administrative metadata (region, division, province, municipality, barangay).
"""

import pandas as pd
from .utils import SOURCE_NSBI, fix_swapped_coords, has_valid_coords, normalize_school_id

RAW_PATH = "data/raw/SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.xlsx"


def load(project_root):
    """Load and normalize NSBI 2023-2024 school list.

    Parameters
    ----------
    project_root : str or Path
        Root directory of the project.

    Returns
    -------
    pd.DataFrame
        Normalized DataFrame with columns: school_id, school_name, latitude,
        longitude, region, division, province, municipality, barangay, source.
    """
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
    renamed = renamed[has_valid_coords(renamed)].copy()
    renamed["source"] = SOURCE_NSBI

    out_cols = [
        "school_id", "school_name", "latitude", "longitude",
        "region", "division", "province", "municipality", "barangay", "source",
    ]
    return renamed[out_cols].reset_index(drop=True)
