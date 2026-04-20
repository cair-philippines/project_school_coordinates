"""Shared utilities for the coordinates pipeline."""

import numpy as np

# Canonical column order for normalized source DataFrames
COORD_COLS = ["school_id", "latitude", "longitude"]
LOCATION_COLS = ["region", "province", "municipality", "barangay"]
IDENTITY_COLS = ["school_id", "school_name"]
STANDARD_COLS = IDENTITY_COLS + ["latitude", "longitude"] + LOCATION_COLS

# Philippines bounding box (shared by public and private pipelines)
PH_LAT_MIN, PH_LAT_MAX = 4.5, 21.5
PH_LON_MIN, PH_LON_MAX = 116.0, 127.0

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


def fix_swapped_coords(df, source_label=""):
    """Auto-correct rows whose latitude/longitude are clearly swapped.

    A row is considered swapped when its reported latitude falls inside the PH
    longitude band AND its reported longitude falls inside the PH latitude band,
    but the original orientation does not. In practice this catches cases where
    a user entered (lon, lat) instead of (lat, lon).

    Mutates a copy of df and returns (df, n_fixed). Source_label is used for logs.
    """
    import pandas as pd

    if "latitude" not in df.columns or "longitude" not in df.columns:
        return df, 0

    out = df.copy()
    lat = pd.to_numeric(out["latitude"], errors="coerce").to_numpy().copy()
    lon = pd.to_numeric(out["longitude"], errors="coerce").to_numpy().copy()

    in_lat_band = (lat >= PH_LAT_MIN) & (lat <= PH_LAT_MAX)
    in_lon_band = (lon >= PH_LON_MIN) & (lon <= PH_LON_MAX)
    swapped_orientation = (lon >= PH_LAT_MIN) & (lon <= PH_LAT_MAX) & (lat >= PH_LON_MIN) & (lat <= PH_LON_MAX)

    # Only fix when current orientation does NOT look PH-valid but the swapped one does
    swap_mask = swapped_orientation & ~(in_lat_band & in_lon_band)
    n_fixed = int(swap_mask.sum())

    if n_fixed > 0:
        # Swap via intermediate copies to avoid aliasing the view we read from
        new_lat = lat.copy()
        new_lon = lon.copy()
        new_lat[swap_mask] = lon[swap_mask]
        new_lon[swap_mask] = lat[swap_mask]
        out["latitude"] = new_lat
        out["longitude"] = new_lon
        if source_label:
            print(f"  [{source_label}] Fixed {n_fixed:,} swapped lat/lon rows")

    return out, n_fixed


def reject_out_of_ph_bounds(df, source_label=""):
    """Null out coordinates that fall outside the PH bounding box.

    Use AFTER fix_swapped_coords. Rows with coords outside [4.5-21.5, 116-127]
    have their latitude and longitude set to NaN. The row is retained so the
    school is not dropped — the coordinate cascade will fall back to lower
    priority sources for it.

    Returns (df, n_rejected).
    """
    import pandas as pd

    if "latitude" not in df.columns or "longitude" not in df.columns:
        return df, 0

    out = df.copy()
    lat = pd.to_numeric(out["latitude"], errors="coerce")
    lon = pd.to_numeric(out["longitude"], errors="coerce")

    in_bounds = (
        (lat >= PH_LAT_MIN) & (lat <= PH_LAT_MAX)
        & (lon >= PH_LON_MIN) & (lon <= PH_LON_MAX)
    )
    has_coord = lat.notna() & lon.notna()
    reject_mask = has_coord & ~in_bounds
    n_rejected = int(reject_mask.sum())

    if n_rejected > 0:
        out.loc[reject_mask, "latitude"] = np.nan
        out.loc[reject_mask, "longitude"] = np.nan
        if source_label:
            print(f"  [{source_label}] Rejected {n_rejected:,} out-of-PH-bounds rows")

    return out, n_rejected


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in kilometers."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))
