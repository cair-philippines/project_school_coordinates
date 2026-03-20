# Unified School Coordinates — Philippine Schools

Reproducible pipelines that consolidate school geolocation data from multiple DepEd sources into canonical coordinates tables for Philippine public and private schools.

## Problem

DepEd maintains school coordinates across multiple systems that frequently disagree — sometimes by kilometers. School IDs also change over time (e.g., when a school's curricular offering is reclassified), making it difficult to track the same physical school across datasets. There is no single authoritative source for public schools, and the only private school coordinate source is self-reported with significant quality issues.

## Solution

Two separate pipelines address the distinct challenges of each sector:

### Public Schools

1. **Normalizes** four coordinate sources into a common schema
2. **Resolves historical school ID changes** via a crosswalk built from official mappings and spatial+name deduplication
3. **Selects coordinates** through a trust-based priority cascade reflecting DepEd's valuation of each source
4. **Attaches administrative location columns** (region, province, municipality, barangay) from the best available source
5. **Tracks lineage** so every coordinate can be traced back to its origin

### Private Schools

1. **Cleans self-reported coordinates** (fixes swapped lat/lon, rejects invalid and out-of-bounds values)
2. **Merges** cleaned coordinates with the official LIS universe to ensure complete coverage
3. **Preserves GASTPE participation flags** (ESC, SHS VP, JDVP) for policy analysis
4. **Tracks cleaning status** so every coordinate carries its provenance

## Data Sources

### Public Schools (4 sources, priority cascade)

| Priority | Source | Description | Schools |
|---|---|---|---|
| 1 | DepEd Data Encoding Monitoring Sheet | University-validated coordinates for flagged mismatches | ~7,700 |
| 2 | OSMapaaralan (OpenStreetMap) | Human-validated school footprints via OSM mapping | ~44,400 |
| 3 | SY 2023-2024 List of Schools (NSBI) | Official school infrastructure inventory | ~47,200 |
| 4 | Geolocation of Public Schools | Internal DepEd office revision | ~47,400 |

### Private Schools (1 source, coordinate cleaning)

| Source | Description | Schools |
|---|---|---|
| Private School Seats and TOSF (Oct 2025) | Self-reported via Google Forms + LIS master list | 12,011 |

## Output

### Public Schools — 48,369 schools, 100% coordinate coverage

| File | Description |
|---|---|
| `data/modified/public_school_coordinates.parquet` | Canonical coordinates table |
| `data/modified/public_school_id_crosswalk.parquet` | Historical → canonical school ID mapping (80,333 entries) |
| `data/modified/public_school_coordinates.csv` | CSV export of coordinates table |
| `data/modified/public_school_coordinates.xlsx` | Excel workbook (Metadata + Coordinates + Crosswalk) |
| `output/build_public_report.txt` | Pipeline run summary and statistics |

### Private Schools — 12,011 schools, 74.2% coordinate coverage

| File | Description |
|---|---|
| `data/modified/private_school_coordinates.parquet` | Cleaned coordinates table |
| `data/modified/private_school_coordinates.csv` | CSV export |
| `data/modified/private_school_coordinates.xlsx` | Excel workbook (Metadata + Private School Coordinates) |
| `output/build_private_report.txt` | Pipeline run summary and statistics |

### Public School Coordinates Schema

| Column | Description |
|---|---|
| `school_id` | Canonical (most recent) DepEd LIS School ID |
| `school_name` | Best available school name |
| `latitude` | Final latitude |
| `longitude` | Final longitude |
| `coord_source` | Which source provided the coordinates |
| `monitoring_chosen_source` | Sub-source chosen by validator (if applicable) |
| `sources_available` | All sources with coordinates for this school |
| `region` | Administrative region |
| `province` | Province |
| `municipality` | City or municipality |
| `barangay` | Barangay |
| `location_source` | Which source provided the admin fields |

### School ID Crosswalk Schema

| Column | Description |
|---|---|
| `historical_id` | Any school ID ever used |
| `canonical_id` | Most recent / current school ID |
| `match_method` | `official_mapping` or `spatial_name` |
| `year_first_seen` | Earliest SY this historical ID appears |
| `year_last_seen` | Latest SY this historical ID appears |

### Private School Coordinates Schema

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

## Usage

### Prerequisites

Python 3.11+ with `pandas`, `openpyxl`, `pyarrow`, and `numpy`.

### Running the Pipelines

```bash
cd project_coordinates/

# Public schools
python scripts/build_coordinates.py

# Private schools
python scripts/build_private_coordinates.py
```

Both pipelines are deterministic and re-runnable. All outputs are regenerated from the raw source files in `data/raw/`.

## Project Structure

```
project_coordinates/
├── data/
│   ├── raw/                              # Untouched source files (not committed)
│   └── modified/                         # Pipeline outputs
├── scripts/
│   ├── build_coordinates.py              # Public school pipeline orchestrator
│   └── build_private_coordinates.py      # Private school pipeline orchestrator
├── modules/
│   ├── __init__.py
│   ├── build_crosswalk.py                # School ID crosswalk (Layer 1 + 2)
│   ├── load_monitoring.py                # Public: Source A loader
│   ├── load_osmapaaralan.py              # Public: Source B loader
│   ├── load_nsbi.py                      # Public: Source C loader
│   ├── load_geolocation.py               # Public: Source D loader
│   ├── load_private_tosf.py              # Private: TOSF loader + coordinate cleaning
│   └── utils.py                          # Shared helpers
├── documentation/
│   ├── pipeline_plan.md                  # Public pipeline design and decisions
│   ├── technical_notes.md                # Public processing and transformation details
│   ├── private_pipeline_plan.md          # Private pipeline design and decisions
│   └── private_technical_notes.md        # Private processing and transformation details
├── notebooks/                            # Ad-hoc analysis
├── output/                               # Build reports
└── README.md
```

## Documentation

### Public Schools
- **[Pipeline Plan](documentation/pipeline_plan.md)** — objective, source descriptions, priority cascade rationale, step-by-step design, output schemas, and design decisions.
- **[Technical Notes](documentation/technical_notes.md)** — comprehensive processing details: source ingestion, column mappings, crosswalk algorithms, threshold choices, validation results, and known limitations.

### Private Schools
- **[Pipeline Plan](documentation/private_pipeline_plan.md)** — objective, source description, coordinate cleaning strategy, output schema, and design decisions.
- **[Technical Notes](documentation/private_technical_notes.md)** — comprehensive processing details: ingestion, three-pass coordinate cleaning, merge logic, validation results, and known limitations.
