"""Private school loader: Private School Seats and TOSF data collection.

Loads two sheets from the TOSF Excel file:
  - SCHOOLS WITHOUT SUBMISSION: full private school universe from LIS
  - RAW DATA: self-reported coordinates and GASTPE participation

Includes coordinate cleaning (swap fix, invalid rejection, PH bounds check).
"""

import pandas as pd
import numpy as np
from .utils import normalize_school_id

RAW_PATH = "data/raw/Private School Seats and TOSF ao 2025Oct27.xlsx"

# Philippines bounding box
PH_LAT_MIN, PH_LAT_MAX = 4.5, 21.5
PH_LON_MIN, PH_LON_MAX = 116.0, 127.0


def load_universe(project_root):
    """Load the full private school universe from SCHOOLS WITHOUT SUBMISSION.

    Parameters
    ----------
    project_root : str
        Project root directory.

    Returns
    -------
    pd.DataFrame
        Columns: school_id, school_name, region, division, province,
        municipality, barangay, submitted.
    """
    df = pd.read_excel(
        f"{project_root}/{RAW_PATH}",
        sheet_name="SCHOOLS WITHOUT SUBMISSION",
        header=5,
        dtype=str,
    )

    renamed = df.rename(columns={
        "beis_school_id": "school_id",
        "School Name": "school_name",
        "Region": "region",
        "Division": "division",
        "Province": "province",
        "Municipality": "municipality",
        "Barangay": "barangay",
        "Has the school Submitted the GForm?": "submitted",
    })

    renamed["school_id"] = normalize_school_id(renamed["school_id"])
    renamed = renamed.dropna(subset=["school_id"])
    renamed["submitted"] = renamed["submitted"].str.strip().str.lower() == "yes"

    out_cols = [
        "school_id", "school_name", "region", "division",
        "province", "municipality", "barangay", "submitted",
    ]
    return renamed[out_cols].reset_index(drop=True)


def load_coordinates(project_root):
    """Load and clean coordinates from RAW DATA sheet.

    Returns the cleaned coordinates along with GASTPE flags and
    per-row cleaning status.

    Parameters
    ----------
    project_root : str
        Project root directory.

    Returns
    -------
    pd.DataFrame
        Columns: school_id, latitude, longitude, coord_status,
        coord_rejection_reason, esc_participating, shsvp_participating,
        jdvp_participating.
    dict
        Cleaning statistics: counts for each category.
    """
    df = pd.read_excel(
        f"{project_root}/{RAW_PATH}",
        sheet_name="RAW DATA",
        header=7,
        dtype=str,
    )

    # Use Validated School Data as canonical ID, fall back to BEIS School ID
    df["school_id"] = df["Validated School Data"].fillna(df["BEIS School ID"])
    df["school_id"] = normalize_school_id(df["school_id"])
    df = df.dropna(subset=["school_id"])

    # Deduplicate — keep first submission per school
    df = df.drop_duplicates(subset="school_id", keep="first").copy()

    # Parse coordinates
    df["latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")

    # GASTPE flags
    df["esc_participating"] = (df["ESC"].str.strip() == "1").astype(int)
    df["shsvp_participating"] = (df["SHS VP"].str.strip() == "1").astype(int)
    df["jdvp_participating"] = (df["JDVP"].str.strip() == "1").astype(int)

    # Initialize cleaning columns
    df["coord_status"] = "valid"
    df["coord_rejection_reason"] = None

    stats = {
        "total_submissions": len(df),
        "fixed_swap": 0,
        "rejected_invalid": 0,
        "rejected_out_of_bounds": 0,
        "valid": 0,
    }

    # --- Pass 1: Fix swapped lat/lon ---
    lat = df["latitude"].values.copy()
    lon = df["longitude"].values.copy()

    swapped = (
        (lon >= PH_LAT_MIN) & (lon <= PH_LAT_MAX) &
        (lat >= PH_LON_MIN) & (lat <= PH_LON_MAX)
    )
    swap_mask = swapped & ~(
        (lat >= PH_LAT_MIN) & (lat <= PH_LAT_MAX) &
        (lon >= PH_LON_MIN) & (lon <= PH_LON_MAX)
    )
    n_swapped = int(swap_mask.sum())
    df.loc[swap_mask, "latitude"] = lon[swap_mask]
    df.loc[swap_mask, "longitude"] = lat[swap_mask]
    df.loc[swap_mask, "coord_status"] = "fixed_swap"
    stats["fixed_swap"] = n_swapped

    # --- Pass 2: Reject clearly invalid ---
    lat = df["latitude"].values
    lon = df["longitude"].values
    invalid = (
        pd.isna(lat) | pd.isna(lon) |
        ~np.isfinite(lat) | ~np.isfinite(lon) |
        (np.abs(lat) > 90) | (np.abs(lon) > 180) |
        (lat == 0) | (lon == 0)
    )
    # Only reject rows not already marked valid/fixed
    reject_invalid = invalid & (df["coord_status"] != "no_coords")
    df.loc[reject_invalid, "latitude"] = np.nan
    df.loc[reject_invalid, "longitude"] = np.nan
    df.loc[reject_invalid, "coord_status"] = "no_coords"
    df.loc[reject_invalid, "coord_rejection_reason"] = "invalid"
    stats["rejected_invalid"] = int(reject_invalid.sum())

    # --- Pass 3: Reject out-of-PH bounds ---
    lat = df["latitude"].values
    lon = df["longitude"].values
    out_of_bounds = (
        df["coord_status"] != "no_coords"
    ) & (
        (lat < PH_LAT_MIN) | (lat > PH_LAT_MAX) |
        (lon < PH_LON_MIN) | (lon > PH_LON_MAX)
    )
    df.loc[out_of_bounds, "latitude"] = np.nan
    df.loc[out_of_bounds, "longitude"] = np.nan
    df.loc[out_of_bounds, "coord_status"] = "no_coords"
    df.loc[out_of_bounds, "coord_rejection_reason"] = "out_of_bounds"
    stats["rejected_out_of_bounds"] = int(out_of_bounds.sum())

    stats["valid"] = int((df["coord_status"].isin(["valid", "fixed_swap"])).sum())

    out_cols = [
        "school_id", "latitude", "longitude",
        "coord_status", "coord_rejection_reason",
        "esc_participating", "shsvp_participating", "jdvp_participating",
    ]
    return df[out_cols].reset_index(drop=True), stats
