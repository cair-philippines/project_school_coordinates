# Response: Private School Coordinate Validation — Action Taken

**From:** project_coordinates
**To:** project_ugnay
**Date:** 2026-03-25
**Re:** `prompt_private_school_coordinate_validation.md`

---

## Summary

The suspect coordinate issue identified by project_ugnay has been addressed. A new **Pass 4 (suspect coordinate detection)** was added to the private school pipeline in project_coordinates. The affected schools are now flagged with `coord_status = "suspect"` in the regenerated output at `data/modified/private_school_coordinates.parquet`.

## What Changed

### New cleaning pass in `modules/load_private_tosf.py`

Pass 4 runs after the existing 3-pass cleaning (swap fix → invalid reject → PH bounds reject) and flags coordinates that are technically valid but spatially implausible:

| Sub-check | Detection Method | Schools Flagged |
|---|---|---|
| **4a — Known placeholders** | Coordinates within ~110m of known TOSF defaults: `(14.57929, 121.06494)` and `(14.61789, 121.10269)` | 488 |
| **4b — Coordinate clusters** | 3+ schools from different municipalities sharing exact coordinates | 62 |
| **4c — Round numbers** | Both lat and lon have <3 decimal places (precision coarser than ~100m) | 220 |
| **Total** | | **770** |

### New `coord_status` value: `suspect`

Flagged schools retain their coordinates (not set to null) but are marked with:
- `coord_status = "suspect"` (previously `valid`)
- `coord_rejection_reason` = one of `placeholder_default`, `coordinate_cluster`, `round_coordinates`

### Impact on the dataset

| Metric | Before | After |
|---|---|---|
| `valid` | 8,809 | 8,054 |
| `fixed_swap` | 105 | 90 |
| `suspect` (new) | 0 | 770 |
| `no_coords` | 3,253 | 3,253 |

## How project_ugnay Should Use This

### Filtering suspect coordinates

For spatial analysis (distance computation, catchment mapping, accessibility metrics), exclude suspect schools:

```python
df = pd.read_parquet('path/to/private_school_coordinates.parquet')
reliable = df[df['coord_status'].isin(['valid', 'fixed_swap'])]
```

This removes the 770 suspect schools from distance calculations, eliminating the bogus edges caused by the placeholder coordinate.

### The specific schools project_ugnay flagged

- The **469 schools** at `(14.57929, 121.06494)` are now tagged as `suspect` / `placeholder_default`. After deduplication in the pipeline, 466 exact matches + 22 near-variants = 488 total flagged under this reason.
- The **16 schools** at `(14.0, 121.0)`, **9 at `(14.0, 120.0)`**, and **7 at `(15.0, 120.0)`** are flagged as `coordinate_cluster`.
- The **7 schools** at `(14.61789, 121.10269)` are flagged as `placeholder_default`.

### PSGC validation provides additional evidence

The PSGC point-in-polygon validation (`psgc_validation` column) still runs on suspect schools. Most placeholder schools receive `psgc_mismatch` because their coordinate is in NCR but they're administratively in another region. This provides a second independent signal of coordinate incorrectness.

## Design Decisions

1. **Flag, not reject** — coordinates are preserved (not set to null) so they can be visually inspected in Piring and used for non-spatial analysis. Downstream projects filter with `coord_status != "suspect"`.

2. **Tight placeholder tolerance** — 0.001 degrees (~110m) instead of a wider radius. Prevents false-flagging legitimate schools in the San Juan/Pasig area where the default coordinate happens to be.

3. **Generalized detection** — Pass 4b (clustering) catches future placeholder values without needing to know them in advance. If the TOSF system changes its default coordinate, the cluster detector will surface it once 3+ schools from different municipalities share it.

## Commit Reference

- Commit: `d9039c8` on `cair-philippines/project_school_coordinates`
- Files changed: `modules/load_private_tosf.py`, `scripts/build_private_coordinates.py`, `data/modified/private_school_coordinates.*`, documentation
