"""PSGC spatial validation via point-in-polygon.

Two levels of validation:
1. Barangay-level: tests whether coordinates fall within claimed PSGC barangay
   (psgc_match / psgc_mismatch / psgc_no_validation — metadata only)
2. Municipal-level: tests whether coordinates fall within declared municipality,
   flags schools that are in the wrong municipality or over water as suspect
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path

SHAPEFILE_PATH = "data/modified/phl_admbnda_adm4_updated/phl_admbnda_adm4_updated.shp"


def _load_shapefile(project_root):
    """Load barangay shapefile and prepare for spatial joins."""
    shp_path = Path(project_root) / SHAPEFILE_PATH
    gdf = gpd.read_file(shp_path)

    # Strip 'PH' prefix from PSGC codes to get pure 10-digit numeric
    for col in ["ADM4_PCODE", "ADM3_PCODE", "ADM2_PCODE", "ADM1_PCODE"]:
        gdf[col] = gdf[col].str.replace("PH", "", regex=False)

    return gdf


def spatial_lookup(project_root, df):
    """Perform point-in-polygon lookup for schools with coordinates.

    Returns both barangay and municipality PSGC codes from the polygon
    the school's coordinate falls in.

    Parameters
    ----------
    project_root : str
        Project root directory.
    df : pd.DataFrame
        Schools DataFrame with latitude, longitude columns.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with new columns:
        - psgc_observed_barangay: 10-digit barangay code from polygon
        - psgc_observed_municity: municipality code from polygon (first 7 digits + 000)
        Both are None if the point falls outside all polygons (over water).
    """
    print("  Loading shapefile...")
    gdf = _load_shapefile(project_root)

    # Filter to schools with valid coordinates
    has_coords = df["latitude"].notna() & df["longitude"].notna()
    coords_df = df[has_coords].copy()

    if len(coords_df) == 0:
        df["psgc_observed_barangay"] = None
        df["psgc_observed_municity"] = None
        return df

    print(f"  Performing point-in-polygon for {len(coords_df):,} schools...")

    # Create GeoDataFrame from school points
    geometry = [Point(lon, lat) for lon, lat in zip(coords_df["longitude"], coords_df["latitude"])]
    schools_gdf = gpd.GeoDataFrame(
        coords_df[["school_id"]],
        geometry=geometry,
        crs="EPSG:4326",
    )

    # Spatial join: find which barangay polygon each school falls in
    # Carry both ADM4_PCODE (barangay) and ADM3_PCODE (municipality)
    joined = gpd.sjoin(
        schools_gdf,
        gdf[["ADM4_PCODE", "ADM3_PCODE", "geometry"]],
        how="left",
        predicate="within",
    )

    # Handle duplicates (school on polygon boundary may match multiple)
    joined = joined.drop_duplicates(subset="school_id", keep="first")

    # Map results back to original DataFrame
    lookup_brgy = joined.set_index("school_id")["ADM4_PCODE"]
    lookup_muni = joined.set_index("school_id")["ADM3_PCODE"]

    df["psgc_observed_barangay"] = df["school_id"].map(lookup_brgy)
    df["psgc_observed_municity"] = df["school_id"].map(lookup_muni)

    matched = df["psgc_observed_barangay"].notna().sum()
    over_water = has_coords.sum() - matched
    print(f"  Matched to polygon: {matched:,}")
    print(f"  Outside all polygons (over water/unmapped): {over_water:,}")

    return df


def validate(df):
    """Compare claimed vs observed PSGC barangay and tag results.

    This is barangay-level metadata — it does NOT flag coord_status.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: psgc_barangay (claimed), psgc_observed_barangay,
        latitude, longitude.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with new column `psgc_validation`.
    """
    has_coords = df["latitude"].notna() & df["longitude"].notna()
    has_claimed = df["psgc_barangay"].notna()
    has_observed = df["psgc_observed_barangay"].notna()

    # Default: no validation possible
    df["psgc_validation"] = "psgc_no_validation"

    # Match: both claimed and observed exist and are equal
    both = has_claimed & has_observed
    match_mask = both & (df["psgc_barangay"] == df["psgc_observed_barangay"])
    df.loc[match_mask, "psgc_validation"] = "psgc_match"

    # Mismatch: both exist but differ
    mismatch_mask = both & (df["psgc_barangay"] != df["psgc_observed_barangay"])
    df.loc[mismatch_mask, "psgc_validation"] = "psgc_mismatch"

    # Summary
    match_count = match_mask.sum()
    mismatch_count = mismatch_mask.sum()
    no_val = len(df) - match_count - mismatch_count
    print(f"\n  PSGC barangay validation:")
    print(f"    psgc_match:         {match_count:,}")
    print(f"    psgc_mismatch:      {mismatch_count:,}")
    print(f"    psgc_no_validation: {no_val:,}")

    return df


def validate_municipality(df):
    """Municipal-level coordinate validation.

    Flags schools whose coordinates fall in the wrong municipality or
    outside all polygons (over water). Updates coord_status to 'suspect'
    for flagged schools.

    Two checks:
    1. Over water: school has coordinates but falls outside all polygons
    2. Wrong municipality: school's observed municipality differs from
       its claimed psgc_municity

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: latitude, longitude, coord_status,
        coord_rejection_reason, psgc_municity (claimed),
        psgc_observed_municity (from spatial_lookup).

    Returns
    -------
    pd.DataFrame
        Input DataFrame with coord_status updated for flagged schools.
    """
    has_coords = df["latitude"].notna() & df["longitude"].notna()

    # Initialize coord_status if not present (public pipeline doesn't have it)
    if "coord_status" not in df.columns:
        df["coord_status"] = None
        df.loc[has_coords, "coord_status"] = "valid"
        df.loc[~has_coords, "coord_status"] = "no_coords"
    if "coord_rejection_reason" not in df.columns:
        df["coord_rejection_reason"] = None

    # Only check schools that currently have valid or fixed_swap status
    checkable = has_coords & df["coord_status"].isin(["valid", "fixed_swap"])

    # Check 1: Over water — has coordinates but no polygon match
    no_polygon = checkable & df["psgc_observed_municity"].isna()
    n_water = int(no_polygon.sum())
    if n_water > 0:
        df.loc[no_polygon, "coord_status"] = "suspect"
        df.loc[no_polygon, "coord_rejection_reason"] = "over_water"

    # Check 2: Wrong municipality — observed municipality differs from claimed
    has_claimed_muni = df["psgc_municity"].notna() & (df["psgc_municity"] != "None")
    has_observed_muni = df["psgc_observed_municity"].notna()

    # Extract municipality portion from PSGC codes for comparison
    # psgc_municity is 10-digit (e.g., 0102906000), ADM3_PCODE is 7-digit (e.g., 0102906)
    # Normalize both to 7-digit municipality code
    both_muni = checkable & has_claimed_muni & has_observed_muni
    if both_muni.any():
        subset = df.loc[both_muni].copy()
        claimed_7 = subset["psgc_municity"].str[:7]
        observed_7 = subset["psgc_observed_municity"].str[:7]
        mismatch_idx = subset.index[claimed_7.values != observed_7.values]
        # Don't double-flag schools already marked as suspect (e.g., over_water)
        wrong_muni = df.index.isin(mismatch_idx) & (df["coord_status"] != "suspect")
        n_wrong = int(wrong_muni.sum())
        if n_wrong > 0:
            df.loc[wrong_muni, "coord_status"] = "suspect"
            df.loc[wrong_muni, "coord_rejection_reason"] = "wrong_municipality"
    else:
        n_wrong = 0

    print(f"\n  Municipal-level validation:")
    print(f"    Over water / outside all polygons: {n_water:,}")
    print(f"    Wrong municipality:                {n_wrong:,}")
    print(f"    Total newly flagged as suspect:    {n_water + n_wrong:,}")

    return df
