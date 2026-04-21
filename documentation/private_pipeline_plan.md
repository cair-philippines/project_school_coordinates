# Private School Coordinates Pipeline — Plan

## Objective

Build a reproducible pipeline for private school coordinates that follows the same structure and conventions as the public school pipeline. Produces a canonical coordinates table for Philippine private schools with coordinate cleaning, lineage tracking, and administrative location columns.

Unlike the public school pipeline (which resolves coordinates across four sources via a trust-based priority cascade), the private school pipeline works with a **single self-reported source** where the core challenge is **coordinate quality**, not source selection.

## Source

**File**: `Private School Seats and TOSF ao 2025Oct27.xlsx`

Collected by DepEd's Private Education Office (PEO) via Google Forms, as of October 27, 2025.

| Sheet | Role | Rows | Description |
|---|---|---|---|
| `RAW DATA` | Coordinates + metadata | 10,365 | Self-reported submissions with lat/lon, GASTPE flags, and enrollment seats |
| `SCHOOLS WITHOUT SUBMISSION` | Full private school universe | 13,184 | LIS master list (Sep 2025) with admin metadata and submission status |
| `SUMMARY` | Regional aggregates | — | Not used in pipeline |
| `Sheet2` | Pivot table | — | Not used in pipeline |

### Source Context

- Coordinates are **self-reported by school respondents** via a Google Form — no validation layer like OSMapaaralan or the university monitoring sheet.
- ~8.7% of submitted coordinates fall outside the Philippines bounding box: 116 with swapped lat/lon, 555 clearly invalid (zeros, huge numbers), 230 near but outside PH bounds.
- Two school ID columns exist: `BEIS School ID` (original) and `Validated School Data` (corrected by DepEd). The validated ID is used as canonical; they match for 10,324 of 10,365 rows.
- Some schools submitted multiple times — 10,365 rows but only 9,660 unique BEIS IDs.
- Virtually zero overlap with public school IDs (separate ID ranges).

## Project Structure (additions to existing)

```
modules/
├── load_private_tosf.py              # loader + coordinate cleaning
scripts/
├── build_private_coordinates.py      # orchestrator for private schools
documentation/
├── private_pipeline_plan.md          # this file
├── private_technical_notes.md        # processing details
```

## Pipeline Steps

### Step 0: Setup

- Entry point: `scripts/build_private_coordinates.py`
- Outputs to `data/gold/` (data) and `output/` (report)
- Re-runnable end-to-end with no manual steps

### Step 1: Load & Normalize (`modules/load_private_tosf.py`)

**1a — School universe** (from `SCHOOLS WITHOUT SUBMISSION` sheet)
- Header at row index 5; 13,184 schools
- This is the master list — every private school gets a row, even without coordinates
- Normalize columns: `school_id` (from `beis_school_id`), `school_name`, `region`, `division`, `province`, `municipality`, `barangay`
- Capture `submitted` flag from "Has the school Submitted the GForm?" column

**1b — Coordinates + GASTPE data** (from `RAW DATA` sheet)
- Header at row index 7; 10,365 submissions
- Use `Validated School Data` as canonical school ID (fall back to `BEIS School ID` if null)
- Parse `Latitude` and `Longitude` to numeric
- Extract GASTPE flags: `ESC`, `SHS VP`, `JDVP` (1/0 values)
- Deduplicate: keep first occurrence per school ID

### Step 2: Clean Coordinates

Four-pass cleaning applied to the coordinates from RAW DATA:

| Pass | Condition | Action | Result |
|---|---|---|---|
| **1. Fix swapped** | lon in [4.5, 21.5] AND lat in [116, 127] | Swap lat ↔ lon | ~105 fixed |
| **2. Reject invalid** | null, non-finite, abs(lat) > 90, abs(lon) > 180, or zero | Set coords to null | ~505 rejected |
| **3. Reject out-of-PH** | lat not in [4.5, 21.5] OR lon not in [116, 127] | Set coords to null | ~208 rejected |
| **4. Flag suspect** | Placeholder defaults, coordinate clusters, round numbers | Mark as `suspect` | ~770 flagged |

**Pass 4 (suspect coordinate detection)** addresses coordinates that are technically valid but spatially implausible — they pass passes 1–3 but are almost certainly wrong. Discovered when project_ugnay found 469 schools across all 18 regions sharing the exact same coordinate `(14.57929, 121.06494)` in the San Juan/Pasig area of NCR.

Pass 4 has three sub-checks:
- **4a — Known placeholders**: Coordinates within ~110m of known TOSF system defaults (`14.57929, 121.06494` and `14.61789, 121.10269`). These are pre-filled values that schools never corrected. ~488 schools.
- **4b — Coordinate clusters**: 3+ schools from different municipalities sharing the same exact coordinate. Legitimate co-location would be in the same municipality. ~62 schools.
- **4c — Round numbers**: Both lat and lon have fewer than 3 decimal places (precision coarser than ~100m). Values like `(14.0, 121.0)` are typed-in approximations, not GPS readings. ~220 schools.

Each school receives:
- `coord_status`: `valid`, `fixed_swap`, `suspect`, or `no_coords`
- `coord_rejection_reason`: if no_coords, one of `invalid`, `out_of_bounds`, `no_submission`, `not_in_lis`; if suspect, one of `placeholder_default`, `coordinate_cluster`, `round_coordinates`

### Step 3: Merge Universe + Coordinates

- Left join: universe (12,011) ← cleaned coordinates
- Schools without submission or with rejected coordinates retain null lat/lon
- **Location columns**: sourced from the universe sheet (LIS official metadata — more standardized than self-reported RAW DATA)
- **School name**: prefer universe sheet (official LIS name) over self-reported name
- **GASTPE flags**: joined from RAW DATA where available, null otherwise

### Step 3.5: Enrollment-Based Universe Expansion

The LIS master list may not capture every operational private school. The pipeline expands the universe using enrollment data.

- Load enrollment CSV(s), filter to `sector == "Private"`, deduplicate by school ID
- Identify private schools in enrollment but not in the LIS universe
- Add them with `coord_status = "no_coords"`, `coord_rejection_reason = "not_in_lis"`
- Location columns from enrollment file; GASTPE flags set to 0

**Current result**: 157 private schools added from SY 2024-2025 enrollment data.

### Step 4: Tag Enrollment Status

Every school receives an `enrollment_status` tag:
- `active` — school ID found in SY 2024-2025 enrollment data (private sector)
- `no_enrollment_reported` — school in LIS/TOSF but no enrollment reported

This identifies schools that may have ceased operations or not yet reported. Their coordinates (if any) are retained.

**Current result**: 11,940 active, 228 with no enrollment reported.

### Step 4.5: PSGC Standardization & Spatial Validation

Same process as the public pipeline — see **[PSGC Standardization Plan](psgc_standardization_plan.md)**. Appends PSGC codes and validates coordinates against barangay polygons.

### Step 4.6: Enrollment Metadata Enrichment

Same process as the public pipeline. Enriches with `region` (NIR-aware), `old_region`, `school_management`, `annex_status`, `offers_es/jhs/shs`, `shs_strand_offerings`, and backfills remaining blank school names.

### Step 5: Validation & Report

- Coordinate coverage: how many of the total universe have valid coordinates
- Cleaning statistics: swaps fixed, invalids rejected, out-of-bounds rejected
- Enrollment expansion and status counts
- PSGC validation summary (match/mismatch/no_validation)
- GASTPE participation summary
- Write to `output/build_private_report.txt`

### Step 6: Output

#### Schema

| Column | Description |
|---|---|
| `school_id` | Validated BEIS School ID |
| `school_name` | Official LIS school name |
| `latitude` | Cleaned latitude (null if rejected) |
| `longitude` | Cleaned longitude (null if rejected) |
| `coord_status` | `valid`, `fixed_swap`, or `no_coords` |
| `coord_rejection_reason` | If no_coords: `invalid`, `out_of_bounds`, `no_submission`, `not_in_lis` |
| `region` | Administrative region (NIR-aware) |
| `old_region` | Pre-NIR region naming |
| `division` | Division |
| `province` | Province |
| `municipality` | City or municipality |
| `barangay` | Barangay |
| `esc_participating` | ESC program flag (1/0) |
| `shsvp_participating` | SHS VP flag (1/0) |
| `jdvp_participating` | JDVP flag (1/0) |
| `enrollment_status` | `active` (in enrollment data) or `no_enrollment_reported` |
| `school_management` | School management type |
| `annex_status` | Standalone/Mother/Annex/Mobile |
| `offers_es` | Offers Elementary (True/False) |
| `offers_jhs` | Offers JHS (True/False) |
| `offers_shs` | Offers SHS (True/False) |
| `shs_strand_offerings` | Comma-delimited SHS strands |
| `psgc_region` | 10-digit PSGC region code |
| `psgc_region_name` | PSA region name |
| `psgc_province` | 10-digit PSGC province code |
| `psgc_province_name` | PSA province name |
| `psgc_municity` | 10-digit PSGC municipality/city code |
| `psgc_municity_name` | PSA municipality/city name |
| `psgc_barangay` | 10-digit PSGC barangay code (claimed, from crosswalk) |
| `psgc_barangay_name` | PSA barangay name (claimed) |
| `psgc_observed_barangay` | 10-digit PSGC barangay code (from point-in-polygon) |
| `psgc_validation` | `psgc_match`, `psgc_mismatch`, or `psgc_no_validation` |
| `urban_rural` | Urban/Rural classification (2020 CPH) |
| `income_class` | Municipal income class (DOF) |

#### Output Files

- `data/gold/private_school_coordinates.parquet`
- `data/gold/private_school_coordinates.csv`
- `data/gold/private_school_coordinates.xlsx` — single workbook with two sheets:
  - **Metadata**: pipeline description, source info, run timestamp, summary statistics, cleaning thresholds
  - **Private School Coordinates**: the canonical coordinates table
- `output/build_private_report.txt`

## Design Decisions

1. **Separate pipeline from public schools** — different source characteristics (single self-reported source vs. four validated sources) warrant distinct processing logic rather than forcing both into the same cascade.
2. **Universe comes from SCHOOLS WITHOUT SUBMISSION sheet** — this is the LIS master list and includes schools that didn't submit coordinates. Ensures no private school is silently dropped.
3. **Three-pass coordinate cleaning** — ordered to maximize salvageable coordinates: fix swaps first (recoverable), then reject clearly invalid, then reject out-of-bounds.
4. **Philippines bounding box [4.5–21.5, 116–127]** — generous bounds covering all Philippine territory including Tawi-Tawi (south) and Batanes (north).
5. **Location columns from universe, not self-reported** — the LIS master list has standardized admin metadata; the Google Form responses have inconsistent formatting (e.g., "Province of Laguna" vs "Laguna" vs "LAGUNA").
6. **GASTPE flags preserved** — ESC, SHS VP, and JDVP participation is useful context for downstream policy analysis.
7. **Enrollment data expands the universe and tags status.** Schools in enrollment but not in LIS are added with null coordinates and `not_in_lis` rejection reason. All schools receive an `enrollment_status` tag so downstream users can distinguish active schools from those with no reported enrollment.
8. **PSGC is appended, not replacing DepEd locality columns.** Spatial validation flags mismatches for review without auto-correcting. See [PSGC Standardization Plan](psgc_standardization_plan.md).

## Related Documentation

- **[Private Technical Notes](private_technical_notes.md)** — processing and transformation details
- **[Public Pipeline Plan](pipeline_plan.md)** — companion pipeline for public schools
