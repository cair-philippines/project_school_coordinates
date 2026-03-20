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
- Outputs to `data/modified/` (data) and `output/` (report)
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

Three-pass cleaning applied to the coordinates from RAW DATA:

| Pass | Condition | Action | Expected |
|---|---|---|---|
| **Fix swapped** | lon in [4.5, 21.5] AND lat in [116, 127] | Swap lat ↔ lon | ~116 |
| **Reject invalid** | null, non-finite, abs(lat) > 90, abs(lon) > 180, or zero | Set coords to null | ~555 |
| **Reject out-of-PH** | lat not in [4.5, 21.5] OR lon not in [116, 127] | Set coords to null | ~230 |

Each school receives:
- `coord_status`: `valid`, `fixed_swap`, or `no_coords`
- `coord_rejection_reason`: if no_coords, one of `invalid`, `out_of_bounds`, or `no_submission`

### Step 3: Merge Universe + Coordinates

- Left join: universe (13,184) ← cleaned coordinates
- Schools without submission or with rejected coordinates retain null lat/lon
- **Location columns**: sourced from the universe sheet (LIS official metadata — more standardized than self-reported RAW DATA)
- **School name**: prefer universe sheet (official LIS name) over self-reported name
- **GASTPE flags**: joined from RAW DATA where available, null otherwise

### Step 4: Validation & Report

- Coordinate coverage: how many of 13,184 have valid coordinates
- Cleaning statistics: swaps fixed, invalids rejected, out-of-bounds rejected
- GASTPE participation summary
- Write to `output/build_private_report.txt`

### Step 5: Output

#### Schema

| Column | Description |
|---|---|
| `school_id` | Validated BEIS School ID |
| `school_name` | Official LIS school name |
| `latitude` | Cleaned latitude (null if rejected) |
| `longitude` | Cleaned longitude (null if rejected) |
| `coord_status` | `valid`, `fixed_swap`, or `no_coords` |
| `coord_rejection_reason` | If no_coords: `invalid`, `out_of_bounds`, `no_submission` |
| `region` | Administrative region |
| `division` | Division |
| `province` | Province |
| `municipality` | City or municipality |
| `barangay` | Barangay |
| `esc_participating` | ESC program flag (1/0) |
| `shsvp_participating` | SHS VP flag (1/0) |
| `jdvp_participating` | JDVP flag (1/0) |

#### Output Files

- `data/modified/private_school_coordinates.parquet`
- `data/modified/private_school_coordinates.csv`
- `data/modified/private_school_coordinates.xlsx` — single workbook with two sheets:
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

## Related Documentation

- **[Private Technical Notes](private_technical_notes.md)** — processing and transformation details
- **[Public Pipeline Plan](pipeline_plan.md)** — companion pipeline for public schools
