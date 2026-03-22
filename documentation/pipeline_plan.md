# Unified School Coordinates Pipeline — Plan

## Objective

Build a durable, reproducible pipeline that consolidates school coordinate data from four DepEd sources into a single canonical table of Philippine public schools. Each school receives one authoritative latitude/longitude pair, selected through a trust-based priority cascade that reflects DepEd's valuation of each source. The output tracks coordinate lineage (which source was chosen and why) and retains administrative location columns (region, province, municipality, barangay) for downstream spatial analysis.

Because DepEd school IDs change over time (e.g., when an elementary school begins offering high school and is reclassified), the pipeline also builds a **school ID crosswalk** — a lookup table mapping any known historical school ID to its current canonical ID. All source data is remapped to canonical IDs before the coordinate cascade runs, ensuring that the same physical school is never split across multiple rows due to ID changes.

Additionally, the pipeline expands its school universe using enrollment data, ensuring that schools with reported enrollment but absent from all coordinate sources are still included in the output (flagged as having no coordinates).

**Final output**: one row per canonical school ID with coordinates, lineage, and location context, plus a crosswalk table for historical ID resolution.

## Sources & Priority Cascade

| Priority | Source | Label | Description |
|---|---|---|---|
| 1 | Monitoring Sheet (sheets 1–5) | `monitoring_validated` | ~8,570 schools validated by university team; highest trust |
| 2 | OSMapaaralan GeoJSON | `osmapaaralan` | ~44K features; human-validated via OSM mapping process |
| 3 | SY 2023-2024 List of Schools | `nsbi_2324` | ~47K schools; official but dated NSBI system |
| 4 | Geolocation of Public Schools ("Geolocations" tab) | `geolocation_deped` | ~47K schools; internal office revision |
| 5 | DRRMS IMRS 2025 | `drrms_imrs` | ~16K schools; self-reported via disaster incident reports |

### Source Context

- **Monitoring Sheet**: A university in the Philippines conducted a second round of human validation on ~11,331 public schools that DepEd flagged for coordinate mismatches beyond an internal threshold. Validators compared NSBI and OSMapaaralan coordinates, chose the correct one (or found a new location), and recorded the validated result. Of these, ~8,570 have final validated coordinates. The remaining ~2,761 were marked Ambiguous or Not Found.
- **OSMapaaralan**: School footprints mapped in OpenStreetMap through a rigorous community mapping process. The `ref` property holds DepEd school IDs. Geometry is mostly polygons (centroids extracted for lat/lon).
- **SY 2023-2024 List of Schools**: Generated from DepEd's official National School Building Inventory (NSBI) system. Contains the broadest administrative metadata (region, division, province, municipality, barangay).
- **Geolocation of Public Schools**: A file maintained by an internal DepEd office that may contain revised/updated coordinates from the NSBI system, but is considered less authoritative than the other sources. Also contains the **School ID Mapping** tab used to build the crosswalk.
- **DRRMS IMRS 2025**: Coordinates collected via DepEd's Disaster Risk Reduction Management Service Incident Management Reporting System. Each row is a disaster report filed by a school official — schools may have multiple reports. Self-reported and unvalidated, but 100% of coordinates fall within PH bounds. Deduplicated to one row per school.

## Project Structure

```
project_coordinates/
├── data/
│   ├── raw/                          # untouched source files
│   │   ├── 02. DepEd Data Encoding Monitoring Sheet.xlsx
│   │   ├── osmapaaralan_overpass_turbo_export.geojson
│   │   ├── SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.xlsx
│   │   ├── Geolocation of Public Schools_DepEd.xlsx
│   │   ├── DRRMS IMRS data 2025.csv
│   │   └── project_bukas_enrollment_2024-25.csv
│   └── modified/                     # pipeline outputs
├── scripts/
│   └── build_coordinates.py          # orchestrator
├── modules/
│   ├── __init__.py
│   ├── build_crosswalk.py            # school ID crosswalk (Layer 1 + 2)
│   ├── load_monitoring.py            # Source A loader
│   ├── load_osmapaaralan.py          # Source B loader
│   ├── load_nsbi.py                  # Source C loader
│   ├── load_geolocation.py           # Source D loader
│   ├── load_drrms.py                 # Source E loader (DRRMS IMRS)
│   ├── load_enrollment.py            # enrollment-based universe expansion
│   └── utils.py                      # shared helpers
├── notebooks/
├── output/                           # build_public_report.txt
├── documentation/
│   └── pipeline_plan.md              # this file
└── README.md
```

## Pipeline Steps

### Step 0: Setup

- Entry point: `scripts/build_coordinates.py`
- Outputs to `data/modified/` (data) and `output/` (report)
- Re-runnable end-to-end with no manual steps

### Step 1: Load & Normalize Each Source

Each `modules/load_*.py` handles ingestion and normalization for its source and returns a clean DataFrame with consistent column names.

**Source A — Monitoring Sheet** (`modules/load_monitoring.py`)
- Stack sheets "1" through "5", header at row index 1
- Keep only rows where `Findings == "Validated"` AND validated lon/lat are non-null
- Normalize to: `school_id`, `latitude`, `longitude`, `region`, `division`, `barangay`, `school_name`
- Preserve `Source` column as `monitoring_chosen_source` (OSMapaaralan / NSBI / New coordinates)

**Source B — OSMapaaralan** (`modules/load_osmapaaralan.py`)
- Load GeoJSON features; extract `ref` as `school_id`
- Drop features with no valid `ref`
- Polygon/MultiPolygon → compute centroid; Point → use directly
- Extract available location properties: `addr:province`, `addr:city`/`addr:town`/`addr:village`, `name`

**Source C — SY 2023-2024 List of Schools** (`modules/load_nsbi.py`)
- Sheet `DB`, header at row index 5
- Normalize to: `school_id`, `latitude`, `longitude`, `region`, `division`, `province`, `municipality`, `barangay`, `school_name`
- Drop rows with null coordinates

**Source D — Geolocation of Public Schools** (`modules/load_geolocation.py`)
- Sheet `Geolocations`, header at row index 0
- Normalize to: `school_id`, `latitude`, `longitude`, `region`, `division`, `province`, `municipality`, `barangay`, `school_name`
- Drop rows with null coordinates

**Source E — DRRMS IMRS 2025** (`modules/load_drrms.py`)
- Load CSV; each row is a disaster report, not a school
- Normalize column names (`deped school id number` → `school_id`, `municipality/city` → `municipality`)
- Normalize region names from long format ("REGION V (BICOL REGION)") to short format ("Region V")
- Deduplicate by school_id, keeping first report per school
- Drop rows with null coordinates
- Normalize province/municipality/barangay to title case

### Step 1.5: Build School ID Crosswalk

The crosswalk maps any known historical school ID to its current canonical ID (most recent). Built in two layers by `modules/build_crosswalk.py`.

**Layer 1 — Official mapping (School ID Mapping tab)**
- Parse the `sy_2005`–`sy_2024` columns from the "School ID Mapping" sheet in `Geolocation of Public Schools_DepEd.xlsx`
- For each school entity (row), the canonical ID is the most recent non-null ID
- Emit one row per distinct historical ID: `(historical_id, canonical_id, match_method="official_mapping", year_first_seen, year_last_seen)`

**Layer 2 — Spatial + name deduplication**
- After Layer 1, identify school IDs across all 4 sources that are NOT covered by the crosswalk
- For these orphan IDs, find potential matches using:
  - **Spatial proximity**: schools within ~100m of each other
  - **Name similarity**: fuzzy string matching to confirm (prevents false matches on co-located but distinct schools)
- Emit rows with `match_method="spatial_name"` to distinguish confidence level
- Schools that split or merge are not force-matched

**After the crosswalk is built**, all source DataFrames have their `school_id` remapped to canonical IDs. This ensures that the same physical school contributes to a single row in the final output, regardless of which ID each source used.

### Step 2: Establish the School Universe

- Union all unique **canonical** `school_id` values across all 4 remapped sources
- Every school that appears in any source gets a row in the final output, including schools with no coordinates (flagged accordingly)

### Step 2.5: Enrollment-Based Universe Expansion

The four coordinate sources do not capture every operational public school. Some schools have active enrollment but were never included in any geolocation effort. The pipeline expands the universe using enrollment data to ensure completeness.

**Module**: `modules/load_enrollment.py`

**Process**:
1. Load enrollment CSV(s) listed in the `ENROLLMENT_FILES` configuration at the top of the orchestrator script
2. Filter to public schools only, deduplicate by school ID
3. Remap enrollment IDs through the crosswalk (enrollment data may use historical IDs)
4. Identify enrollment schools not found in the coordinate universe
5. Add these schools to the universe with null coordinates

**Generalized design**: The enrollment loader accepts any school-level enrollment CSV with a `school_id` and `sector` column. Column name variants are resolved via an alias mapping. New enrollment files can be added by appending to the `ENROLLMENT_FILES` list — no code changes required.

**Current enrollment file**: `project_bukas_enrollment_2024-25.csv` (47,972 public schools; 563 not found in any coordinate source)

These 562 schools receive:
- `coord_source = None` (no coordinates available)
- `sources_available = "enrollment_only"`
- `location_source = "enrollment"` (admin metadata from the enrollment file)

### Step 3: Apply Priority Cascade

For each `school_id`, select coordinates from the **first available** source in order:

1. Monitoring (validated)
2. OSMapaaralan
3. NSBI 2023-2024
4. Geolocation DepEd
5. DRRMS IMRS 2025

Record per school:
- `coord_source` — which source provided the final lat/lon
- `monitoring_chosen_source` — if from monitoring, which sub-source the validator chose (else null)
- `sources_available` — comma-separated list of all sources that had coordinates for this school

### Step 4: Attach Location Columns

- Pull `region`, `province`, `municipality`, `barangay` from the best available administrative source
- Location column priority (independent of coordinate priority): NSBI 2023-2024 → Geolocation DepEd → Monitoring Sheet → OSMapaaralan → DRRMS IMRS → Enrollment
- For enrollment-only schools (no coordinate source), location columns come from the enrollment file
- Record `location_source` to track provenance of admin fields

### Step 4.5: PSGC Standardization & Spatial Validation

Appends PSGC codes and PSA-standard names, then validates coordinates against barangay polygons. See **[PSGC Standardization Plan](psgc_standardization_plan.md)** for full details.

**Process**:
1. Load PSGC crosswalk (`modules/load_psgc.py`) — maps school_id → PSGC codes/names, pads codes to 10 digits
2. Left-join to coordinates dataset by school_id; backfill blank school names from PSGC crosswalk
3. Load barangay shapefile (`modules/validate_psgc.py`) and perform point-in-polygon for all schools with coordinates
4. Compare claimed PSGC barangay (from crosswalk) vs observed (from spatial lookup) and tag as `psgc_match`, `psgc_mismatch`, or `psgc_no_validation`

### Step 4.6: Enrollment Metadata Enrichment

Enriches the output with metadata from the enrollment file (`project_bukas_enrollment_2024-25.csv`):
- Backfill remaining blank school names
- Add `region` (NIR-aware) and `old_region` (pre-NIR); for NIR schools, `old_region` is derived by mapping NIR provinces back to Region VI/VII
- Add `school_management`, `annex_status`, `offers_es`, `offers_jhs`, `offers_shs`
- Derive `shs_strand_offerings` (comma-delimited) from non-zero SHS enrollment by strand
- PSO schools (35) are excluded from the enrollment file

### Step 5: Validation & Report

- Flag schools with no coordinates from any source
- Flag schools where available sources disagree by >1 km (large discrepancy)
- Summary counts by `coord_source`, `location_source`, coverage rates
- Crosswalk statistics: total entries, Layer 1 vs Layer 2 counts, IDs remapped
- Write to `output/build_public_report.txt`

### Step 6: Output

#### Unified School Coordinates Schema

| Column | Description |
|---|---|
| `school_id` | Canonical (most recent) DepEd LIS School ID |
| `school_name` | Best available name |
| `latitude` | Final latitude |
| `longitude` | Final longitude |
| `coord_source` | Source that provided coordinates |
| `monitoring_chosen_source` | Sub-source chosen by validator (if applicable) |
| `sources_available` | All sources that had coordinates for this school; `enrollment_only` if only known from enrollment |
| `region` | Administrative region (NIR-aware, from enrollment file) |
| `old_region` | Pre-NIR region naming (Negros Occidental in Region VI, Negros Oriental/Siquijor in Region VII) |
| `province` | Province |
| `municipality` | City or municipality |
| `barangay` | Barangay |
| `location_source` | Source that provided admin fields |
| `enrollment_status` | `active` (in enrollment data) or `no_enrollment_reported` |
| `school_management` | School management type (DepEd, Non-Sectarian, Sectarian, SUC, etc.) |
| `annex_status` | Standalone School, Mother School, Annex/Extension School, Mobile School/Center |
| `offers_es` | Whether the school offers Elementary (True/False) |
| `offers_jhs` | Whether the school offers Junior High School (True/False) |
| `offers_shs` | Whether the school offers Senior High School (True/False) |
| `shs_strand_offerings` | Comma-delimited SHS strands (e.g., "ABM,HUMSS,STEM,TVL") |
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

#### School ID Crosswalk Schema

| Column | Description |
|---|---|
| `historical_id` | Any school ID ever used for this school |
| `canonical_id` | Most recent / current school ID |
| `match_method` | `official_mapping` or `spatial_name` |
| `year_first_seen` | Earliest SY this ID appears (null if from spatial match) |
| `year_last_seen` | Latest SY this ID appears (null if from spatial match) |

#### Output Files

- `data/modified/public_school_coordinates.parquet`
- `data/modified/public_school_coordinates.csv`
- `data/modified/public_school_id_crosswalk.parquet`
- `data/modified/public_school_coordinates.xlsx` — single workbook with three sheets:
  - **Metadata**: pipeline description, source priority, run timestamp, summary statistics
  - **Unified School Coordinates**: the canonical coordinates table
  - **School ID Crosswalk**: historical-to-canonical ID mapping
- `output/build_public_report.txt`

## Design Decisions

1. **Coordinate priority follows DepEd's trust hierarchy**, with the Monitoring Sheet elevated to top priority because it represents a second round of human validation on flagged mismatches.
2. **Location column priority is independent of coordinate priority.** NSBI leads for admin fields because it has the most complete region/province/municipality/barangay coverage.
3. **Schools with no coordinates are included** in the output and flagged, rather than silently dropped.
4. **Modular design**: each source has its own loader module, keeping preprocessing isolated and testable. The orchestrator script handles only the merge logic.
5. **School ID crosswalk is built before the cascade** so that ID changes are resolved before coordinate selection. This prevents the same physical school from appearing as multiple rows.
6. **Crosswalk uses two layers** with distinct confidence levels: official mapping (authoritative) and spatial+name matching (heuristic). The `match_method` column lets downstream users filter by confidence.
7. **Canonical ID is always the most recent ID**, reflecting DepEd's current administrative state.
8. **Enrollment data expands the universe, not the coordinates.** Enrollment files identify schools that exist but have no geolocation data. These are included with null coordinates rather than silently excluded, ensuring the output is a complete roster of known public schools. The enrollment loader is generalized to accept any future enrollment CSV.
9. **Private schools are excluded from public sources after crosswalk remapping.** OSMapaaralan contains both public and private school footprints. Known private school IDs (from the TOSF LIS universe and enrollment data) are removed from all public source DataFrames after ID remapping, preventing sector duplication in the outputs.
10. **PSGC is appended, not replacing DepEd locality columns.** The existing location columns from DepEd sources are retained alongside new PSGC-standardized columns. Spatial validation flags mismatches for human review without auto-correcting.

## Related Documentation

- **[Technical Notes](technical_notes.md)** — comprehensive record of all processing and transformation decisions: source ingestion details, column mappings, crosswalk algorithms, threshold choices, validation results, and known limitations.
- **[PSGC Standardization Plan](psgc_standardization_plan.md)** — PSGC crosswalk, spatial validation, and tagging methodology.
