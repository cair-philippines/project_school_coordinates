"""Shared enrollment metadata enrichment (used by both public and private).

Backfills school_name from enrollment, attaches school_management, annex_status,
curricular offerings, SHS strand offerings, and populates the NIR-aware region
column while preserving old_region.

The logic is identical across both pipelines — centralized here so a
divergence in one doesn't silently skew the other output.
"""

from . import load_enrollment


def enrich(result, project_root):
    """Enrich a coordinate DataFrame with metadata from the enrollment silver.

    Parameters
    ----------
    result : pd.DataFrame
        Must contain school_id. May contain school_name, region, old_region
        (any missing columns are created/filled).
    project_root : str
        Project root; enrollment silver is read from there.

    Returns
    -------
    pd.DataFrame
        Modified in place (and returned). Adds/fills:
          school_name (backfill), region (NIR-aware), old_region,
          school_management, annex_status, offers_es/jhs/shs,
          shs_strand_offerings.
    """
    print("\nEnriching from enrollment silver...")
    try:
        meta = load_enrollment.load_full_metadata(project_root)
    except FileNotFoundError:
        print("  Enrollment silver not found, skipping enrichment")
        return result

    # Retain the original single-iteration scoping so the diff stays minimal.
    for _ in [0]:
        print(f"  Enrollment metadata: {len(meta):,} schools")

        meta_indexed = meta.set_index("school_id")

        # Backfill school_name from enrollment where still blank
        blank_name = result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")
        in_meta = result["school_id"].isin(meta_indexed.index)
        backfill_name = blank_name & in_meta
        if backfill_name.sum() > 0:
            fill_ids = result.loc[backfill_name, "school_id"]
            result.loc[backfill_name, "school_name"] = meta_indexed.loc[
                fill_ids.values, "school_name"
            ].values
            print(f"  School names backfilled from enrollment: {backfill_name.sum():,}")

        enroll_cols = [
            "school_management", "annex_status",
            "offers_es", "offers_jhs", "offers_shs", "shs_strand_offerings",
        ]
        for col in enroll_cols:
            if col not in result.columns:
                result[col] = None
            matched = result["school_id"].isin(meta_indexed.index)
            fill_ids = result.loc[matched, "school_id"]
            if len(fill_ids) > 0 and col in meta_indexed.columns:
                result.loc[matched, col] = meta_indexed.loc[
                    fill_ids.values, col
                ].values

        # NIR-aware region handling: preserve pre-NIR naming in old_region,
        # place NIR-aware (current) region in region column.
        if "old_region" not in result.columns:
            result["old_region"] = result["region"]

        result["region_new"] = None
        matched = result["school_id"].isin(meta_indexed.index)
        fill_ids = result.loc[matched, "school_id"]
        if len(fill_ids) > 0:
            result.loc[matched, "region_new"] = meta_indexed.loc[
                fill_ids.values, "region"
            ].values

        no_new_region = result["region_new"].isna() | (result["region_new"] == "None")
        result.loc[no_new_region, "region_new"] = result.loc[no_new_region, "old_region"]

        no_old = result["old_region"].isna() | (result["old_region"] == "None")
        in_meta_old = no_old & result["school_id"].isin(meta_indexed.index)
        if in_meta_old.sum() > 0:
            fill_ids = result.loc[in_meta_old, "school_id"]
            result.loc[in_meta_old, "old_region"] = meta_indexed.loc[
                fill_ids.values, "old_region"
            ].values

        result["region"] = result["region_new"]
        result = result.drop(columns=["region_new"])

        print(f"  Enriched: {matched.sum():,} / {len(result):,}")

    remaining_blank = (result["school_name"].isna() | (result["school_name"] == "None") | (result["school_name"] == "")).sum()
    print(f"  Remaining blank school names: {remaining_blank:,}")

    return result
