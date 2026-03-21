"""Shared utilities for the coordinates pipeline."""

import numpy as np

# Canonical column order for normalized source DataFrames
COORD_COLS = ["school_id", "latitude", "longitude"]
LOCATION_COLS = ["region", "province", "municipality", "barangay"]
IDENTITY_COLS = ["school_id", "school_name"]
STANDARD_COLS = IDENTITY_COLS + ["latitude", "longitude"] + LOCATION_COLS

# Source labels
SOURCE_MONITORING = "monitoring_validated"
SOURCE_OSM = "osmapaaralan"
SOURCE_NSBI = "nsbi_2324"
SOURCE_GEOLOCATION = "geolocation_deped"
SOURCE_DRRMS = "drrms_imrs"

# Priority order for coordinate selection
COORD_PRIORITY = [SOURCE_MONITORING, SOURCE_OSM, SOURCE_NSBI, SOURCE_GEOLOCATION, SOURCE_DRRMS]

# Priority order for location columns
LOCATION_PRIORITY = [SOURCE_NSBI, SOURCE_GEOLOCATION, SOURCE_MONITORING, SOURCE_OSM, SOURCE_DRRMS]


def has_valid_coords(df):
    """Return boolean mask for rows with non-null, finite lat/lon."""
    return (
        df["latitude"].notna()
        & df["longitude"].notna()
        & np.isfinite(df["latitude"])
        & np.isfinite(df["longitude"])
    )


def normalize_school_id(value):
    """Normalize a school ID — works on both a pandas Series and a scalar.

    Strips whitespace and removes trailing '.0' from float-like strings.
    Returns a cleaned Series or a scalar string (None if empty/null).
    """
    import pandas as pd

    if isinstance(value, pd.Series):
        return value.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    # Scalar
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip().replace(".0", "") if str(value).strip().endswith(".0") else str(value).strip()
    return s if s else None


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in kilometers."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))
