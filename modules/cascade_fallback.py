"""Cascade fallback for schools with suspect coordinates.

When the primary coordinate cascade picks a high-priority source's coordinates
that later turn out to be suspect (outside all polygons or in the wrong
municipality), fall back to the next-priority source whose coordinates pass
municipal validation. Records the originating source in `coord_fallback_from`.

Runs after validate_municipality, before suspect Pass 4, so Pass 4 can still
flag an implausible fallback.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union

from .utils import COORD_PRIORITY
from .validate_psgc import BOUNDARY_BUFFER_DEG, SHAPEFILE_PATH


def _build_municipal_polygon_cache(project_root):
    """Load the shapefile and group barangay polygons by municipality.

    Returns a dict keyed by 7-digit ADM3_PCODE → buffered municipal polygon.
    Populated lazily per-muni code as needed to avoid paying the full
    per-polygon dissolve cost upfront.
    """
    shp_path = Path(project_root) / SHAPEFILE_PATH
    gdf = gpd.read_file(shp_path)
    gdf["ADM3_PCODE"] = gdf["ADM3_PCODE"].str.replace("PH", "", regex=False)
    return {"_gdf": gdf, "_cache": {}}


def _muni_polygon(store, muni_code):
    """Get (or build) the buffered dissolved polygon for a municipality code."""
    if muni_code in store["_cache"]:
        return store["_cache"][muni_code]
    polys = store["_gdf"][store["_gdf"]["ADM3_PCODE"] == muni_code]
    if len(polys) == 0:
        store["_cache"][muni_code] = None
        return None
    dissolved = unary_union(polys.geometry)
    buffered = dissolved.buffer(BOUNDARY_BUFFER_DEG)
    store["_cache"][muni_code] = buffered
    return buffered


def _ncr_muni_match(claimed_7, observed_7):
    """Mirror of validate_psgc's NCR sub-district normalization."""
    if claimed_7 is None or observed_7 is None:
        return False
    if len(claimed_7) != 7 or len(observed_7) != 7:
        return False
    if claimed_7 == observed_7:
        return True
    if claimed_7[:5] != observed_7[:5]:
        return False
    return claimed_7[5:7] == "00" or observed_7[5:7] == "00"


def apply_fallback(result, sources, project_root):
    """Swap in lower-priority source coordinates for suspect schools.

    A suspect school's coordinates are replaced by the next-priority source's
    coordinates only if (a) an alternative source has this school and (b) the
    alternative coordinates fall within the claimed municipality polygon (with
    the same 200m buffer used by validate_municipality). When swapped:

      - latitude, longitude are updated
      - coord_source is updated to the alternative source
      - coord_fallback_from records the original source
      - coord_status is reset to 'valid'
      - coord_rejection_reason is cleared
      - psgc_observed_municity and psgc_observed_barangay are recomputed

    If no alternative passes, the row stays suspect with its original values.

    Returns the modified DataFrame.
    """
    result = result.copy()
    if "coord_fallback_from" not in result.columns:
        result["coord_fallback_from"] = None

    suspect = result["coord_status"] == "suspect"
    if not suspect.any():
        print("\n  Cascade fallback: 0 suspect schools, skipping")
        return result

    eligible_ids = set(result.loc[suspect, "school_id"])
    if not eligible_ids:
        return result

    store = _build_municipal_polygon_cache(project_root)

    # Index each source by school_id for lookup
    indexed_sources = {}
    for label, df in sources.items():
        deduped = df.drop_duplicates(subset="school_id", keep="first")
        indexed_sources[label] = deduped.set_index("school_id")

    n_promoted = 0
    promotions_by_src = {}

    # For each school currently suspect, try lower-priority alternatives in order.
    for idx in result.index[suspect]:
        school_id = result.at[idx, "school_id"]
        current_src = result.at[idx, "coord_source"]
        claimed_muni = result.at[idx, "psgc_municity"]
        if claimed_muni is None or pd.isna(claimed_muni):
            continue
        claimed_7 = str(claimed_muni)[:7]

        try:
            current_priority = COORD_PRIORITY.index(current_src)
        except ValueError:
            continue  # unknown source, skip

        for alt_src in COORD_PRIORITY[current_priority + 1:]:
            alt_df = indexed_sources.get(alt_src)
            if alt_df is None or school_id not in alt_df.index:
                continue
            alt_row = alt_df.loc[school_id]
            alt_lat = alt_row.get("latitude")
            alt_lon = alt_row.get("longitude")
            if pd.isna(alt_lat) or pd.isna(alt_lon):
                continue

            poly = _muni_polygon(store, claimed_7)
            if poly is None:
                continue
            if not poly.contains(Point(alt_lon, alt_lat)):
                continue

            # Point is inside the claimed municipality — promote.
            result.at[idx, "latitude"] = alt_lat
            result.at[idx, "longitude"] = alt_lon
            result.at[idx, "coord_source"] = alt_src
            result.at[idx, "coord_fallback_from"] = current_src
            result.at[idx, "coord_status"] = "valid"
            result.at[idx, "coord_rejection_reason"] = None

            # Recompute observed polygon codes by exact point-in-polygon
            gdf = store["_gdf"]
            hit = gdf[gdf.geometry.contains(Point(alt_lon, alt_lat))]
            if len(hit) > 0:
                result.at[idx, "psgc_observed_municity"] = hit.iloc[0]["ADM3_PCODE"]
                result.at[idx, "psgc_observed_barangay"] = hit.iloc[0]["ADM4_PCODE"]

            n_promoted += 1
            promotions_by_src[alt_src] = promotions_by_src.get(alt_src, 0) + 1
            break  # stop at first valid alternative

    print(f"\n  Cascade fallback: {n_promoted:,} suspect schools promoted to valid via lower-priority alternatives")
    if n_promoted > 0:
        for src, n in sorted(promotions_by_src.items(), key=lambda x: -x[1]):
            print(f"    via {src}: {n:,}")

    return result
