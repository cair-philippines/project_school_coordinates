"""Build the School ID Crosswalk.

Maps any known historical school ID to its current canonical ID (most recent).
Two layers:
  Layer 1 — Official mapping from the "School ID Mapping" tab
  Layer 2 — Spatial + name deduplication for orphan IDs
"""

from pathlib import Path

import pandas as pd
import numpy as np
from difflib import SequenceMatcher

from . import load_sos_mapping
from .utils import normalize_school_id, haversine_km

# SY columns in chronological order
SY_COLS = [f"sy_{y}" for y in range(2005, 2025)]

# Spatial + name matching thresholds
DISTANCE_THRESHOLD_KM = 0.1  # 100 meters
NAME_SIMILARITY_THRESHOLD = 0.6


def _load_enrollment_ids(project_root):
    """Load school IDs from the enrollment silver for canonical reconciliation.

    Used to reconcile the transient 7-digit school_id_2024 format (ID with
    a leading '1' prepended) back to the canonical 6-digit form.
    """
    from . import load_enrollment
    try:
        df = load_enrollment.read_silver(project_root)
        return set(df["school_id"].dropna().str.strip())
    except FileNotFoundError:
        return set()


def _build_layer1(project_root):
    """Layer 1: Extract ID transitions from the official School ID Mapping tab.

    For each row (school entity), collect all distinct IDs across:
      - old_school_id, old_school_id.1
      - BEIS School ID
      - sy_2005 through sy_2024
      - school_id_2024

    The canonical ID is school_id_2024 (most recent). Each historical ID that
    differs from the canonical gets a crosswalk entry.

    Returns
    -------
    pd.DataFrame
        Columns: historical_id, canonical_id, match_method, year_first_seen,
        year_last_seen
    """
    df = load_sos_mapping.read_silver(project_root)

    enrollment_ids = _load_enrollment_ids(project_root)
    if enrollment_ids:
        print(f"  Loaded {len(enrollment_ids):,} enrollment IDs for canonical reconciliation")
    else:
        print("  No enrollment file provided — 7-digit canonicals will not be reconciled")

    records = []
    seen_pairs = set()
    unresolved_7digit = []
    reconciled_7digit = 0

    for _, row in df.iterrows():
        raw_canonical = normalize_school_id(row.get("school_id_2024"))
        if not raw_canonical:
            continue

        # Reconcile the transient 7-digit format (a leading '1' prepended to the
        # standard 6-digit DepEd LIS ID) that appeared in school_id_2024 for
        # ~7,000 schools. DepEd reverted to 6-digit by SY 2024-25 — verify the
        # stripped form exists in that enrollment universe before adopting it.
        transient_7digit = None
        if len(raw_canonical) == 7 and raw_canonical.startswith("1"):
            candidate = raw_canonical[1:]
            if candidate in enrollment_ids:
                canonical = candidate
                transient_7digit = raw_canonical
                reconciled_7digit += 1
            else:
                unresolved_7digit.append(raw_canonical)
                canonical = raw_canonical
        else:
            canonical = raw_canonical

        # Collect all IDs this school entity has ever used
        historical_ids = {}

        # Emit the transient 7-digit form as a historical ID so any stale data
        # source still containing "1XXXXXX" gets remapped to the 6-digit
        # canonical by remap_source().
        if transient_7digit and transient_7digit != canonical:
            historical_ids[transient_7digit] = {"first": 2024, "last": 2024}

        # From SY columns — track year ranges
        for col in SY_COLS:
            val = normalize_school_id(row.get(col))
            if val and val != canonical:
                year = int(col.split("_")[1])
                if val not in historical_ids:
                    historical_ids[val] = {"first": year, "last": year}
                else:
                    historical_ids[val]["first"] = min(historical_ids[val]["first"], year)
                    historical_ids[val]["last"] = max(historical_ids[val]["last"], year)

        # From old_school_id columns (no year info)
        for col in ["old_school_id", "old_school_id.1"]:
            val = normalize_school_id(row.get(col))
            if val and val != canonical and val not in historical_ids:
                historical_ids[val] = {"first": None, "last": None}

        # From BEIS School ID
        beis = normalize_school_id(row.get("BEIS School ID"))
        if beis and beis != canonical and beis not in historical_ids:
            historical_ids[beis] = {"first": None, "last": None}

        # Emit crosswalk entries
        for hist_id, years in historical_ids.items():
            pair = (hist_id, canonical)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                records.append({
                    "historical_id": hist_id,
                    "canonical_id": canonical,
                    "match_method": "official_mapping",
                    "year_first_seen": years["first"],
                    "year_last_seen": years["last"],
                })

        # Also add self-mapping for canonical ID (identity row)
        pair = (canonical, canonical)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            records.append({
                "historical_id": canonical,
                "canonical_id": canonical,
                "match_method": "official_mapping",
                "year_first_seen": None,
                "year_last_seen": None,
            })

    crosswalk = pd.DataFrame(records)
    print(f"  Layer 1 (official mapping): {len(crosswalk):,} entries "
          f"({crosswalk['historical_id'].nunique():,} unique historical IDs)")
    if reconciled_7digit:
        print(f"  Reconciled 7-digit canonicals to 6-digit: {reconciled_7digit:,}")
    if unresolved_7digit:
        print(f"  WARNING: {len(unresolved_7digit):,} 7-digit IDs could not be "
              f"reconciled against 2024-25 enrollment (likely closed/merged)")
    return crosswalk


def _name_similarity(name_a, name_b):
    """Compute normalized similarity between two school names."""
    if not name_a or not name_b:
        return 0.0
    a = str(name_a).lower().strip()
    b = str(name_b).lower().strip()
    return SequenceMatcher(None, a, b).ratio()


def _build_layer2(crosswalk_l1, sources):
    """Layer 2: Spatial + name matching for IDs not covered by Layer 1.

    Finds school IDs across all sources that are not in the crosswalk, then
    checks for spatial proximity + name similarity to link them to existing
    canonical IDs.

    Parameters
    ----------
    crosswalk_l1 : pd.DataFrame
        Layer 1 crosswalk.
    sources : dict
        Source label -> DataFrame with school_id, latitude, longitude, school_name.

    Returns
    -------
    pd.DataFrame
        Additional crosswalk entries from spatial+name matching.
    """
    known_ids = set(crosswalk_l1["historical_id"].unique())

    # Collect all school records not in crosswalk
    orphans = []
    for label, df in sources.items():
        for _, row in df.iterrows():
            sid = row["school_id"]
            if sid and sid not in known_ids:
                orphans.append({
                    "school_id": sid,
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "school_name": row.get("school_name"),
                    "source": label,
                })

    if not orphans:
        print("  Layer 2 (spatial+name): 0 orphan IDs, nothing to match")
        return pd.DataFrame(columns=[
            "historical_id", "canonical_id", "match_method",
            "year_first_seen", "year_last_seen",
        ])

    orphan_df = pd.DataFrame(orphans).drop_duplicates(subset="school_id", keep="first")
    orphan_df = orphan_df.dropna(subset=["latitude", "longitude"])

    # Build a reference set: all canonical IDs with coordinates from sources
    canonical_ids = set(crosswalk_l1["canonical_id"].unique())
    ref_records = []
    for label, df in sources.items():
        for _, row in df.iterrows():
            sid = row["school_id"]
            if sid in canonical_ids:
                ref_records.append({
                    "school_id": sid,
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "school_name": row.get("school_name"),
                })

    if not ref_records:
        print("  Layer 2 (spatial+name): no reference records with coords")
        return pd.DataFrame(columns=[
            "historical_id", "canonical_id", "match_method",
            "year_first_seen", "year_last_seen",
        ])

    ref_df = pd.DataFrame(ref_records).drop_duplicates(subset="school_id", keep="first")
    ref_df = ref_df.dropna(subset=["latitude", "longitude"])

    # Spatial matching: for each orphan, find nearest reference within threshold
    # Use vectorized approach with numpy for efficiency
    orphan_lats = orphan_df["latitude"].values
    orphan_lons = orphan_df["longitude"].values
    ref_lats = ref_df["latitude"].values
    ref_lons = ref_df["longitude"].values

    records = []
    matched_orphans = set()

    for i, (_, orphan) in enumerate(orphan_df.iterrows()):
        if orphan["school_id"] in matched_orphans:
            continue

        # Compute distances to all reference schools
        dists = haversine_km(
            orphan_lats[i], orphan_lons[i],
            ref_lats, ref_lons,
        )

        # Find candidates within threshold
        within = np.where(dists <= DISTANCE_THRESHOLD_KM)[0]
        if len(within) == 0:
            continue

        # Check name similarity for candidates
        best_match = None
        best_sim = 0.0
        for j in within:
            ref_row = ref_df.iloc[j]
            sim = _name_similarity(orphan["school_name"], ref_row["school_name"])
            if sim > best_sim:
                best_sim = sim
                best_match = ref_row

        if best_match is not None and best_sim >= NAME_SIMILARITY_THRESHOLD:
            matched_orphans.add(orphan["school_id"])
            records.append({
                "historical_id": orphan["school_id"],
                "canonical_id": best_match["school_id"],
                "match_method": "spatial_name",
                "year_first_seen": None,
                "year_last_seen": None,
            })

    result = pd.DataFrame(records) if records else pd.DataFrame(columns=[
        "historical_id", "canonical_id", "match_method",
        "year_first_seen", "year_last_seen",
    ])
    print(f"  Layer 2 (spatial+name): {len(orphan_df):,} orphan IDs, "
          f"{len(result):,} matched")
    return result


def build(project_root, sources):
    """Build the complete school ID crosswalk.

    Reads two silver inputs:
      - sos_mapping.parquet (via load_sos_mapping.read_silver) for Layer 1
      - enrollment.parquet  (via load_enrollment.read_silver) for reconciliation

    Parameters
    ----------
    project_root : str
        Project root directory.
    sources : dict
        Source label -> DataFrame (loaded and normalized).

    Returns
    -------
    pd.DataFrame
        Complete crosswalk with columns: historical_id, canonical_id,
        match_method, year_first_seen, year_last_seen.
    """
    print("Building school ID crosswalk...")
    layer1 = _build_layer1(project_root)
    layer2 = _build_layer2(layer1, sources)
    # Ensure consistent dtypes before concat
    for col in ["year_first_seen", "year_last_seen"]:
        layer1[col] = layer1[col].astype("Int64")
        layer2[col] = layer2[col].astype("Int64")
    crosswalk = pd.concat([layer1, layer2], ignore_index=True)
    print(f"  Total crosswalk: {len(crosswalk):,} entries")

    non_6 = (crosswalk["canonical_id"].str.len() != 6).sum()
    if non_6 > 0:
        length_dist = crosswalk["canonical_id"].str.len().value_counts().sort_index().to_dict()
        print(f"  WARNING: {non_6:,} crosswalk entries have non-6-digit canonicals")
        print(f"  Canonical length distribution: {length_dist}")

    # Flag historical_ids that map to multiple canonicals — these are Excel
    # ambiguities that identity-first dedup resolves safely, but still worth
    # surfacing so upstream data can be cleaned.
    ambig = crosswalk.groupby("historical_id")["canonical_id"].nunique()
    ambig_ids = ambig[ambig > 1].index.tolist()
    if ambig_ids:
        print(f"  WARNING: {len(ambig_ids):,} historical IDs map to multiple canonicals "
              f"(Excel ambiguity; resolved by preferring identity mappings)")
        print(f"  Sample: {ambig_ids[:5]}")

    return crosswalk


def _consolidate_duplicates(df):
    """Collapse rows that share a school_id after remapping.

    When 7-digit and 6-digit variants of the same school both appear in a
    source, remapping to the canonical form produces intra-source duplicates.
    Prefer rows with valid coordinates, then rows with a non-empty school_name,
    then stable first-wins.

    Returns
    -------
    tuple of (pd.DataFrame, int)
        Deduplicated DataFrame and the number of rows merged away.
    """
    if not df.duplicated(subset="school_id", keep=False).any():
        return df, 0

    work = df.copy()
    sort_keys, ascending = [], []

    if "latitude" in work.columns and "longitude" in work.columns:
        work["_has_coords"] = work["latitude"].notna() & work["longitude"].notna()
        sort_keys.append("_has_coords")
        ascending.append(False)

    if "school_name" in work.columns:
        names = work["school_name"].astype(str).str.strip()
        work["_has_name"] = work["school_name"].notna() & (names != "") & (names != "None")
        sort_keys.append("_has_name")
        ascending.append(False)

    if sort_keys:
        work = work.sort_values(sort_keys, ascending=ascending, kind="mergesort")

    before = len(work)
    work = work.drop_duplicates(subset="school_id", keep="first")
    work = work.drop(columns=[c for c in ("_has_coords", "_has_name") if c in work.columns])
    work = work.reset_index(drop=True)
    return work, before - len(work)


def _dedupe_crosswalk_identity_first(crosswalk):
    """Deduplicate crosswalk by historical_id, preferring identity mappings.

    When a historical_id has multiple canonical candidates (the Excel has
    ambiguous or contradictory entries — see crosswalk_7digit_reconciliation
    docs), prefer the row where historical_id == canonical_id. This preserves
    a school's self-identity against an upstream Excel entry that tries to
    remap it into a different physical school.

    Only relevant when the historical_id actually IS a canonical in its own
    right (i.e., some Excel row has school_id_2024 equal to this ID).
    """
    xw = crosswalk.copy()
    xw["_is_identity"] = xw["historical_id"] == xw["canonical_id"]
    xw = xw.sort_values("_is_identity", ascending=False, kind="mergesort")
    deduped = xw.drop_duplicates(subset="historical_id", keep="first")
    return deduped.drop(columns="_is_identity")


def remap_source(df, crosswalk):
    """Remap school_id in a source DataFrame using the crosswalk.

    Parameters
    ----------
    df : pd.DataFrame
        Source DataFrame with a school_id column.
    crosswalk : pd.DataFrame
        Crosswalk with historical_id -> canonical_id.

    Returns
    -------
    tuple of (pd.DataFrame, int, int)
        Remapped DataFrame, count of rows whose school_id changed,
        and count of rows merged by intra-source duplicate consolidation.
    """
    deduped = _dedupe_crosswalk_identity_first(crosswalk)
    lookup = deduped.set_index("historical_id")["canonical_id"]
    result = df.copy()
    mapped = result["school_id"].map(lookup)
    # Only remap where a mapping exists; keep original if not in crosswalk
    result["school_id"] = mapped.fillna(result["school_id"])
    remapped_count = (df["school_id"] != result["school_id"]).sum()

    result, merged_count = _consolidate_duplicates(result)
    return result, remapped_count, merged_count
