"""PSGC spatial validation via point-in-polygon.

Loads the Q4 2025 barangay shapefile and tests whether each school's
coordinates fall within its claimed PSGC barangay polygon.

Tags each school as psgc_match, psgc_mismatch, or psgc_no_validation.
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

    Parameters
    ----------
    project_root : str
        Project root directory.
    df : pd.DataFrame
        Schools DataFrame with latitude, longitude columns.

    Returns
    -------
    pd.DataFrame
        Input DataFrame with new column `psgc_observed_barangay` — the
        10-digit PSGC barangay code from the polygon containing the point,
        or None if the point falls outside all polygons.
    """
    print("  Loading shapefile...")
    gdf = _load_shapefile(project_root)

    # Filter to schools with valid coordinates
    has_coords = df["latitude"].notna() & df["longitude"].notna()
    coords_df = df[has_coords].copy()

    if len(coords_df) == 0:
        df["psgc_observed_barangay"] = None
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
    joined = gpd.sjoin(
        schools_gdf,
        gdf[["ADM4_PCODE", "geometry"]],
        how="left",
        predicate="within",
    )

    # Handle duplicates (school on polygon boundary may match multiple)
    joined = joined.drop_duplicates(subset="school_id", keep="first")

    # Map results back to original DataFrame
    lookup = joined.set_index("school_id")["ADM4_PCODE"]
    df["psgc_observed_barangay"] = df["school_id"].map(lookup)

    matched = df["psgc_observed_barangay"].notna().sum()
    unmatched = has_coords.sum() - matched
    print(f"  Matched to barangay polygon: {matched:,}")
    print(f"  No polygon match (outside all boundaries): {unmatched:,}")

    return df


def validate(df):
    """Compare claimed vs observed PSGC barangay and tag results.

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
    print(f"\n  PSGC validation results:")
    print(f"    psgc_match:         {match_count:,}")
    print(f"    psgc_mismatch:      {mismatch_count:,}")
    print(f"    psgc_no_validation: {no_val:,}")

    return df
