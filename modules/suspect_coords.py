"""Suspect coordinate detection (shared by public and private pipelines).

Flags schools whose coordinates are technically valid (inside the PH bounding
box, within the claimed municipality polygon) but spatially or statistically
implausible:

  - placeholder_default: coordinates at a known default/placeholder point
  - coordinate_cluster: 3+ schools share exact coordinates across different
    municipalities (likely a form default or copy-paste error)
  - round_coordinates: both lat and lon have fewer than 3 decimal places
    (likely manual entry with imprecision)

Sets coord_status='suspect' and coord_rejection_reason to one of the above.
Rows already flagged suspect by earlier checks are not re-flagged.
"""

import numpy as np
import pandas as pd


# Known placeholder/default coordinates (lat, lon, tolerance_degrees)
# Tolerance of 0.001 ≈ ~110 meters
KNOWN_PLACEHOLDERS = [
    (14.57929, 121.06494, 0.001),  # TOSF system default — San Juan/Pasig area
    (14.61789, 121.10269, 0.001),  # Possible second default
]

MIN_DECIMAL_PLACES = 3
MIN_CLUSTER_SIZE = 3


def _decimal_places(val):
    """Count decimal places of a float value (trailing zeros ignored)."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0
    s = f"{val:.10f}".rstrip("0")
    if "." in s:
        return len(s.split(".")[1])
    return 0


def detect_placeholder(df, has_coords_mask):
    """Flag rows at a known placeholder coordinate."""
    lat = df["latitude"].values
    lon = df["longitude"].values
    placeholder_mask = np.zeros(len(df), dtype=bool)
    for plat, plon, tol in KNOWN_PLACEHOLDERS:
        placeholder_mask |= has_coords_mask & (
            (np.abs(lat - plat) < tol) & (np.abs(lon - plon) < tol)
        )
    return placeholder_mask


def detect_cluster(df, has_coords_mask, municipality_col):
    """Flag rows whose (lat, lon) rounded to 5 decimals is shared by 3+
    schools across different municipalities.

    Returns boolean Series aligned to df.
    """
    mask = pd.Series(False, index=df.index)
    if municipality_col is None or municipality_col not in df.columns:
        return mask

    coord_schools = df[has_coords_mask].copy()
    if len(coord_schools) == 0:
        return mask

    coord_schools["_lat_r"] = coord_schools["latitude"].round(5)
    coord_schools["_lon_r"] = coord_schools["longitude"].round(5)

    grouped = coord_schools.groupby(["_lat_r", "_lon_r"])
    cluster_idx = []
    for _, group in grouped:
        if len(group) >= MIN_CLUSTER_SIZE:
            munis = group[municipality_col].dropna().astype(str).str.strip().str.lower().unique()
            if len(munis) > 1:
                cluster_idx.extend(group.index.tolist())

    mask.loc[cluster_idx] = True
    return mask


def detect_round(df, has_coords_mask):
    """Flag rows where both lat and lon have fewer than MIN_DECIMAL_PLACES
    decimals (imprecise manual entry).
    """
    mask = pd.Series(False, index=df.index)
    if not has_coords_mask.any():
        return mask

    subset = df[has_coords_mask]
    round_check = subset.apply(
        lambda row: _decimal_places(row["latitude"]) < MIN_DECIMAL_PLACES
                    and _decimal_places(row["longitude"]) < MIN_DECIMAL_PLACES,
        axis=1,
    )
    round_idx = round_check[round_check].index
    mask.loc[round_idx] = True
    return mask


def detect_suspect(df, municipality_col="municipality"):
    """Apply Pass 4 suspect-coord detection in place.

    Only rows currently tagged coord_status ∈ {valid, fixed_swap} are examined.
    Flagged rows get coord_status='suspect' and coord_rejection_reason set.

    Parameters
    ----------
    df : pd.DataFrame
        Must have: school_id, latitude, longitude, coord_status,
        coord_rejection_reason, and a municipality column.
    municipality_col : str
        Column name for municipality (used by cluster detection). Default
        'municipality'.

    Returns
    -------
    pd.DataFrame
        Same DataFrame, modified in place. Also prints a summary.
    """
    # Ensure columns exist
    if "coord_status" not in df.columns:
        df["coord_status"] = None
    if "coord_rejection_reason" not in df.columns:
        df["coord_rejection_reason"] = None

    has_coords = df["coord_status"].isin(["valid", "fixed_swap"])

    n_placeholder = 0
    n_cluster = 0
    n_round = 0

    # Placeholder
    placeholder_mask = detect_placeholder(df, has_coords)
    if placeholder_mask.any():
        df.loc[placeholder_mask, "coord_status"] = "suspect"
        df.loc[placeholder_mask, "coord_rejection_reason"] = "placeholder_default"
        n_placeholder = int(placeholder_mask.sum())

    # Refresh has_coords after placeholder
    has_coords = df["coord_status"].isin(["valid", "fixed_swap"])

    # Cluster
    cluster_mask = detect_cluster(df, has_coords, municipality_col)
    cluster_mask = cluster_mask & (df["coord_status"] != "suspect")
    if cluster_mask.any():
        df.loc[cluster_mask, "coord_status"] = "suspect"
        df.loc[cluster_mask, "coord_rejection_reason"] = "coordinate_cluster"
        n_cluster = int(cluster_mask.sum())

    # Refresh has_coords after cluster
    has_coords = df["coord_status"].isin(["valid", "fixed_swap"])

    # Round
    round_mask = detect_round(df, has_coords)
    round_mask = round_mask & (df["coord_status"] != "suspect")
    if round_mask.any():
        df.loc[round_mask, "coord_status"] = "suspect"
        df.loc[round_mask, "coord_rejection_reason"] = "round_coordinates"
        n_round = int(round_mask.sum())

    print(f"\n  Suspect coordinate detection (Pass 4):")
    print(f"    Placeholder defaults:  {n_placeholder:,}")
    print(f"    Coordinate clusters:   {n_cluster:,}")
    print(f"    Round coordinates:     {n_round:,}")
    print(f"    Total newly flagged:   {n_placeholder + n_cluster + n_round:,}")

    return df
