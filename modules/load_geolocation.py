"""Source D: Geolocation of Public Schools (Geolocations tab).

Internal DepEd file with possibly revised/updated coordinates. Lowest
priority in the cascade. Sheet 'Geolocations', header at row index 0.
"""

import pandas as pd
from .utils import SOURCE_GEOLOCATION, fix_swapped_coords, has_valid_coords, normalize_school_id, reject_out_of_ph_bounds

RAW_PATH = "data/raw/Geolocation of Public Schools_DepEd.xlsx"


def load(project_root):
    """Load and normalize Geolocation of Public Schools.

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
        sheet_name="Geolocations",
        header=0,
        dtype=str,
    )

    renamed = df.rename(columns={
        "School_ID": "school_id",
        "School_Name": "school_name",
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
    renamed, _ = fix_swapped_coords(renamed, source_label=SOURCE_GEOLOCATION)
    renamed, _ = reject_out_of_ph_bounds(renamed, source_label=SOURCE_GEOLOCATION)
    renamed = renamed[has_valid_coords(renamed)].copy()
    renamed["source"] = SOURCE_GEOLOCATION

    out_cols = [
        "school_id", "school_name", "latitude", "longitude",
        "region", "division", "province", "municipality", "barangay", "source",
    ]
    return renamed[out_cols].reset_index(drop=True)
