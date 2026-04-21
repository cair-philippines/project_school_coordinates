"""Private school loader: Private School Seats and TOSF data collection.

Loads two sheets from the TOSF Excel file:
  - SCHOOLS WITHOUT SUBMISSION: full private school universe from LIS
  - RAW DATA: self-reported coordinates and GASTPE participation

Includes coordinate cleaning:
  Pass 1: Fix swapped lat/lon
  Pass 2: Reject invalid coordinates
  Pass 3: Reject out-of-PH bounds
  Pass 4: Flag suspect coordinates (placeholders, clusters, round numbers)
"""

import pandas as pd
import numpy as np
from .utils import normalize_school_id

RAW_PATH = "data/bronze/live/Private School Seats and TOSF ao 2025Oct27.xlsx"

# Philippines bounding box
PH_LAT_MIN, PH_LAT_MAX = 4.5, 21.5
PH_LON_MIN, PH_LON_MAX = 116.0, 127.0

# Known placeholder/default coordinates (lat, lon, tolerance_degrees)
# Tolerance of 0.001 ≈ ~110 meters — tight enough to catch only the
# placeholder and its minor variants, not legitimate nearby schools
KNOWN_PLACEHOLDERS = [
    (14.57929, 121.06494, 0.001),  # TOSF system default — San Juan/Pasig area
    (14.61789, 121.10269, 0.001),  # Possible second default
]

# Minimum decimal precision for coordinates (3 decimal places ≈ 100m)
MIN_DECIMAL_PLACES = 3

# Minimum cluster size to flag as suspect (schools sharing exact coords
# across different municipalities)
MIN_CLUSTER_SIZE = 3


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

    # Deduplicate — keep LAST submission per school. Multiple submissions
    # represent corrections; the later one supersedes the earlier.
    df = df.drop_duplicates(subset="school_id", keep="last").copy()

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

    # --- Pass 4: Flag suspect coordinates ---
    # Only check schools that survived passes 1-3 (status is valid or fixed_swap)
    has_coords = df["coord_status"].isin(["valid", "fixed_swap"])
    stats["suspect_placeholder"] = 0
    stats["suspect_cluster"] = 0
    stats["suspect_round"] = 0

    # Pass 4a: Known placeholder coordinates
    lat = df["latitude"].values
    lon = df["longitude"].values
    for plat, plon, tol in KNOWN_PLACEHOLDERS:
        placeholder_mask = has_coords & (
            (np.abs(lat - plat) < tol) & (np.abs(lon - plon) < tol)
        )
        n_placeholder = int(placeholder_mask.sum())
        if n_placeholder > 0:
            df.loc[placeholder_mask, "coord_status"] = "suspect"
            df.loc[placeholder_mask, "coord_rejection_reason"] = "placeholder_default"
            stats["suspect_placeholder"] += n_placeholder

    # Refresh has_coords after 4a
    has_coords = df["coord_status"].isin(["valid", "fixed_swap"])

    # Pass 4b: Suspicious coordinate clustering
    # Group by exact (lat, lon) rounded to 5 decimal places.
    # If 3+ schools share the same coordinate but are in different municipalities,
    # flag all of them.
    # We need municipality info — get it from the RAW DATA columns.
    if "City or Municipality" in df.columns:
        muni_col = "City or Municipality"
    elif "municipality" in df.columns:
        muni_col = "municipality"
    else:
        muni_col = None

    if muni_col:
        coord_schools = df[has_coords].copy()
        coord_schools["_lat_r"] = coord_schools["latitude"].round(5)
        coord_schools["_lon_r"] = coord_schools["longitude"].round(5)

        grouped = coord_schools.groupby(["_lat_r", "_lon_r"])
        cluster_ids = set()
        for (lat_r, lon_r), group in grouped:
            if len(group) >= MIN_CLUSTER_SIZE:
                munis = group[muni_col].dropna().str.strip().str.lower().unique()
                if len(munis) > 1:
                    cluster_ids.update(group.index)

        # Don't double-flag schools already marked as placeholder
        cluster_mask = df.index.isin(cluster_ids) & (df["coord_status"] != "suspect")
        n_cluster = int(cluster_mask.sum())
        if n_cluster > 0:
            df.loc[cluster_mask, "coord_status"] = "suspect"
            df.loc[cluster_mask, "coord_rejection_reason"] = "coordinate_cluster"
            stats["suspect_cluster"] = n_cluster

    # Refresh has_coords after 4b
    has_coords = df["coord_status"].isin(["valid", "fixed_swap"])

    # Pass 4c: Round number detection
    # Flag coordinates where both lat and lon have fewer than MIN_DECIMAL_PLACES
    # decimal digits (e.g., 14.0, 121.0 or 15.5, 120.0)
    lat = df["latitude"].values
    lon = df["longitude"].values
    precision_factor = 10 ** MIN_DECIMAL_PLACES  # 1000 for 3 decimal places
    round_mask = has_coords & (
        (np.abs(lat * precision_factor - np.round(lat * precision_factor)) < 0.01) &
        (np.abs(lon * precision_factor - np.round(lon * precision_factor)) < 0.01)
    )
    # Only flag if BOTH are round — one round coordinate is common for manual entry
    # but both being round is suspicious
    # Further filter: only flag if fewer than 3 decimal places on BOTH
    def _decimal_places(val):
        """Count decimal places of a float value."""
        s = f"{val:.10f}".rstrip("0")
        if "." in s:
            return len(s.split(".")[1])
        return 0

    if has_coords.any():
        round_check = df[has_coords].apply(
            lambda row: _decimal_places(row["latitude"]) < MIN_DECIMAL_PLACES
                        and _decimal_places(row["longitude"]) < MIN_DECIMAL_PLACES,
            axis=1,
        )
        round_indices = round_check[round_check].index
        # Don't double-flag
        round_final = df.index.isin(round_indices) & (df["coord_status"] != "suspect")
        n_round = int(round_final.sum())
        if n_round > 0:
            df.loc[round_final, "coord_status"] = "suspect"
            df.loc[round_final, "coord_rejection_reason"] = "round_coordinates"
            stats["suspect_round"] = n_round

    stats["valid"] = int((df["coord_status"].isin(["valid", "fixed_swap"])).sum())
    stats["suspect_total"] = stats["suspect_placeholder"] + stats["suspect_cluster"] + stats["suspect_round"]

    out_cols = [
        "school_id", "latitude", "longitude",
        "coord_status", "coord_rejection_reason",
        "esc_participating", "shsvp_participating", "jdvp_participating",
    ]
    return df[out_cols].reset_index(drop=True), stats
