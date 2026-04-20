"""Shared PSGC-joining + spatial validation pipeline.

Used by both public and private orchestrators. The pure shared logic is:
  1. Left-join the PSGC crosswalk on school_id
  2. Backfill blank school_name from psgc_school_name
  3. Point-in-polygon spatial lookup to obtain psgc_observed_barangay/municity
  4. Municipal-level validation (flags suspect / updates coord_status)
  5. Optional cascade fallback for suspect schools (public only)
  6. Optional Pass 4 suspect detection (public only; private already runs it
     inside its raw loader)
  7. Barangay-level validation (metadata, respects coord_status)

Pipeline-specific knobs:
  - sources_for_fallback: if provided, cascade_fallback runs (public pipeline)
  - run_pass4: when True, detect_suspect runs (public pipeline)
"""

from . import load_psgc, validate_psgc, cascade_fallback, suspect_coords


def run(result, project_root, sources_for_fallback=None, run_pass4=False,
        municipality_col="municipality"):
    """Join PSGC + backfill names + spatial validation.

    Parameters
    ----------
    result : pd.DataFrame
        Coordinates DataFrame with at minimum school_id, school_name,
        latitude, longitude.
    project_root : str
        Project root directory (for loading PSGC crosswalk and shapefile).
    sources_for_fallback : dict of {label: DataFrame}, optional
        If provided, cascade_fallback.apply_fallback is invoked between
        municipal validation and Pass 4 suspect detection. Public pipeline
        should pass its remapped source dict; private pipeline should omit.
    run_pass4 : bool
        If True, runs suspect_coords.detect_suspect after fallback (or after
        municipal validation if no fallback). Public pipeline should set True;
        private pipeline already runs Pass 4 inside its loader.
    municipality_col : str
        Column name to use for cluster detection in Pass 4.

    Returns
    -------
    pd.DataFrame
        result with appended PSGC columns and validation flags.
    """
    print("\nAppending PSGC codes...")
    psgc = load_psgc.load(project_root)
    print(f"  PSGC crosswalk: {len(psgc):,} schools")

    result = result.merge(psgc, on="school_id", how="left")
    matched = result["psgc_barangay"].notna().sum()
    print(f"  PSGC matched: {matched:,} / {len(result):,}")

    # Backfill blank school names from the PSGC crosswalk.
    blank_name = result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")
    has_psgc_name = result["psgc_school_name"].notna() & (result["psgc_school_name"] != "None")
    backfill_mask = blank_name & has_psgc_name
    result.loc[backfill_mask, "school_name"] = result.loc[backfill_mask, "psgc_school_name"]
    print(f"  School names backfilled from PSGC: {backfill_mask.sum():,}")
    remaining_blank = (result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")).sum()
    print(f"  Still blank after backfill: {remaining_blank:,}")

    result = result.drop(columns=["psgc_school_name"], errors="ignore")

    print("\nSpatial validation (point-in-polygon)...")
    result = validate_psgc.spatial_lookup(project_root, result)
    # Municipal validation must run BEFORE barangay validation so coord_status
    # is populated when the barangay check decides whether to trust coords.
    result = validate_psgc.validate_municipality(result, project_root=project_root)

    if sources_for_fallback is not None:
        result = cascade_fallback.apply_fallback(
            result, sources_for_fallback, project_root=project_root
        )

    if run_pass4:
        result = suspect_coords.detect_suspect(result, municipality_col=municipality_col)

    result = validate_psgc.validate(result)
    return result
