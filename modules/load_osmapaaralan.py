"""Source B: OSMapaaralan GeoJSON export from Overpass Turbo.

Human-validated school footprints from OpenStreetMap. Geometry is mostly
polygons; centroids are extracted for lat/lon. The `ref` property holds the
DepEd school ID.
"""

import json
import pandas as pd
import numpy as np
from .utils import SOURCE_OSM, fix_swapped_coords, has_valid_coords, normalize_school_id

RAW_PATH = "data/raw/osmapaaralan_overpass_turbo_export.geojson"


def _centroid_of_polygon(coords):
    """Compute centroid of a simple polygon ring (first ring only)."""
    ring = np.array(coords[0])  # exterior ring: [[lon, lat], ...]
    lons = ring[:, 0]
    lats = ring[:, 1]
    return float(np.mean(lons)), float(np.mean(lats))


def _centroid_of_multipolygon(coords):
    """Compute centroid as mean of all polygon centroids."""
    centroids = [_centroid_of_polygon(polygon) for polygon in coords]
    centroids = np.array(centroids)
    return float(np.mean(centroids[:, 0])), float(np.mean(centroids[:, 1]))


def _extract_coords(feature):
    """Extract (longitude, latitude) from a GeoJSON feature."""
    geom = feature.get("geometry")
    if geom is None:
        return None, None

    gtype = geom["type"]
    coords = geom["coordinates"]

    if gtype == "Point":
        return float(coords[0]), float(coords[1])
    elif gtype == "Polygon":
        return _centroid_of_polygon(coords)
    elif gtype == "MultiPolygon":
        return _centroid_of_multipolygon(coords)
    elif gtype == "LineString":
        arr = np.array(coords)
        return float(np.mean(arr[:, 0])), float(np.mean(arr[:, 1]))
    else:
        return None, None


def load(project_root):
    """Load and normalize OSMapaaralan GeoJSON.

    Parameters
    ----------
    project_root : str or Path
        Root directory of the project.

    Returns
    -------
    pd.DataFrame
        Normalized DataFrame with columns: school_id, school_name, latitude,
        longitude, province, municipality, barangay, source.
    """
    with open(f"{project_root}/{RAW_PATH}", "r", encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        ref = props.get("ref")
        if ref is None or str(ref).strip() == "":
            continue

        lon, lat = _extract_coords(feature)

        # Resolve municipality from multiple possible address fields
        municipality = (
            props.get("addr:city")
            or props.get("addr:town")
            or props.get("addr:municipality")
            or props.get("addr:village")
            or props.get("addr:place")
        )

        # Split compound refs (e.g., "132677;304874") into separate records.
        # OSM mappers sometimes enter multiple school IDs for integrated schools
        # that were formed by merging an ES and HS under a new ID.
        ref_parts = [r.strip() for r in str(ref).split(";") if r.strip()]
        for ref_part in ref_parts:
            records.append({
                "school_id": ref_part,
                "school_name": props.get("name"),
                "latitude": lat,
                "longitude": lon,
                "province": props.get("addr:province"),
                "municipality": municipality,
            })

    df = pd.DataFrame(records)
    df["school_id"] = normalize_school_id(df["school_id"])
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df, _ = fix_swapped_coords(df, source_label=SOURCE_OSM)
    df = df[has_valid_coords(df)].copy()
    df["source"] = SOURCE_OSM

    # OSMapaaralan does not have region or barangay in a reliable form
    df["region"] = None
    df["barangay"] = None

    out_cols = [
        "school_id", "school_name", "latitude", "longitude",
        "region", "province", "municipality", "barangay", "source",
    ]
    return df[out_cols].reset_index(drop=True)
