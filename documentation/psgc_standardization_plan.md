# PSGC Standardization & Spatial Validation — Plan

## Objective

Append Philippine Standard Geographic Code (PSGC) codes and PSA-standard locality names to every school in the public and private coordinates datasets, then validate whether each school's coordinates fall within its claimed PSGC barangay polygon. Schools that fail the spatial check are flagged for review.

This does not modify any existing coordinates, location columns, or lineage tracking. It adds new columns alongside the existing data.

## Sources

### PSGC Crosswalk

**File**: `SY 2024-2025 School Level Database WITH PSGC.xlsx`

A manually validated mapping from DepEd school IDs to PSA's PSGC codes, produced by a DepEd office that reconciled DepEd's locality naming with the PSGC. Covers 60,094 schools (47,972 public, 11,939 private, 183 SUCsLUCs). Based on **Q4 2024 PSGC**.

Key columns: `BEIS School ID` → `(PSGC) REGION`, `(PSGC) PROVINCE`, `(PSGC) MUNCIPAL/CITY`, `(PSGC) BARANGAY` (codes) + corresponding `NAME` columns.

**Known issue**: Excel strips leading zeros from PSGC codes. Codes that should be 10 digits (e.g., `0100000000` for Region I) appear as 9 digits (`100000000`). All codes must be left-padded to 10 digits.

### Barangay Shapefile

**File**: `data/reference/phl_admbnda_adm4_updated/phl_admbnda_adm4_updated.shp`

Barangay-level polygons with authoritative PSGC boundaries, updated to **Q4 2025 PSGC** using `cair-philippines/open-data-philippine-maps` update pipeline. Contains ~42,000 barangay polygons.

**PSGC version mismatch**: The Excel crosswalk uses Q4 2024 codes, the shapefile uses Q4 2025. Some codes changed between quarters due to barangay merges, splits, and administrative reorganizations. The shapefile's codes are preferred as the more current reference.

## Pipeline Steps

### Step 1: Load PSGC Crosswalk (`modules/load_psgc.py`)

- Load Excel, sheet `DB`, header at row 6
- Extract `BEIS School ID` and all PSGC columns (codes + names)
- Left-pad all PSGC codes from 9 digits to 10 digits
- Extract `Urban / Rural` and `NEW INCOME CLASSIFICATION` columns
- Deduplicate by school_id (should already be unique — 60,094 rows)
- Return as a lookup table keyed by school_id

### Step 2: Join PSGC to Coordinates

- Left-join public coordinates dataset to the crosswalk by `school_id`
- Left-join private coordinates dataset to the crosswalk by `school_id`
- Schools without a match (~630 public, ~229 private) receive null PSGC codes

### Step 3: Spatial Validation (`modules/validate_psgc.py`)

- Load the barangay shapefile with geopandas
- For each school with coordinates, perform a point-in-polygon test: which barangay polygon contains the school's lat/lon?
- Record the **observed** PSGC barangay code from the spatial lookup

**PSGC version handling**: The point-in-polygon test returns the shapefile's Q4 2025 code. When comparing against the Excel's Q4 2024 claimed code, mismatches may be due to genuine coordinate errors OR due to code changes between Q4 2024 and Q4 2025. The validation tags both codes so the distinction can be made during review.

### Step 4: Compare and Tag

For each school, compare:
- **Claimed PSGC barangay** (from the Excel crosswalk, joined by school_id)
- **Observed PSGC barangay** (from the point-in-polygon test, via coordinates)

| Tag | Meaning |
|---|---|
| `psgc_match` | Claimed barangay matches observed barangay |
| `psgc_mismatch` | Claimed and observed barangays differ |
| `psgc_no_validation` | Cannot validate (no coordinates, no PSGC code, or coordinates fall outside all polygons) |

### Step 4b: Municipal-Level Coordinate Validation

After the barangay-level check, a second validation compares each school's coordinates against its declared municipality polygon. This catches schools that are in the wrong municipality entirely or plotted over water — errors more severe than a barangay-level mismatch.

Two checks:
1. **Over water**: school has coordinates but falls outside all land polygons (observed municipality is null). These are data entry errors — transposed digits, wrong decimal placement, or copy-paste errors.
2. **Wrong municipality**: the observed municipality (from point-in-polygon) differs from the school's declared `psgc_municity`. Comparison uses the first 7 digits of the 10-digit PSGC code.

Schools flagged by either check receive `coord_status = "suspect"` with `coord_rejection_reason` of `over_water` or `wrong_municipality`. This applies to **both public and private** pipelines.

### Step 5: Output

New columns appended to existing public and private parquets:

| Column | Description |
|---|---|
| `psgc_region` | 10-digit PSGC region code |
| `psgc_region_name` | PSA region name |
| `psgc_province` | 10-digit PSGC province code |
| `psgc_province_name` | PSA province name |
| `psgc_municity` | 10-digit PSGC municipality/city code |
| `psgc_municity_name` | PSA municipality/city name |
| `psgc_barangay` | 10-digit PSGC barangay code (claimed, from Excel) |
| `psgc_barangay_name` | PSA barangay name (claimed) |
| `psgc_observed_barangay` | 10-digit PSGC barangay code (from point-in-polygon) |
| `psgc_validation` | `psgc_match`, `psgc_mismatch`, or `psgc_no_validation` |
| `urban_rural` | Urban/Rural classification |
| `income_class` | Municipal income class (1st–5th, from DOF) |

## Project Structure (additions)

```
modules/
├── load_psgc.py                  # PSGC crosswalk loader
├── validate_psgc.py              # Shapefile-based spatial validation
```

## Design Decisions

1. **PSGC is appended, not replacing DepEd locality columns.** The existing `region`, `province`, `municipality`, `barangay` columns from DepEd sources are retained. PSGC columns are added alongside for standardization.
2. **Validation is tagging, not correction.** Mismatches are flagged for human review. The pipeline does not attempt to auto-correct coordinates or administrative assignments.
3. **Shapefile codes (Q4 2025) are preferred for spatial validation.** The point-in-polygon test inherently returns Q4 2025 codes since those are what the shapefile contains. The claimed codes (Q4 2024) may differ due to PSGC updates between quarters — both are recorded so the cause of a mismatch can be distinguished.
4. **Leading zero padding is applied uniformly.** All PSGC codes are normalized to 10 digits to match the shapefile's format and prevent join failures.

## Related Documentation

- **[Pipeline Plan](pipeline_plan.md)** — main coordinates pipeline
- **[Private Pipeline Plan](private_pipeline_plan.md)** — private school pipeline
- **[Open Data Philippine Maps Feedback](open_data_philippine_maps_feedback.md)** — notes on the shapefile source repo
