# Technical Notes — Unified School Coordinates Pipeline

Comprehensive record of all processing and transformation decisions applied to the four DepEd coordinate datasets to produce a single canonical coordinates table and school ID crosswalk.

## 1. Source Ingestion & Normalization

### 1.1 Source A — Monitoring Sheet (`load_monitoring.py`)

**Raw file**: `02. DepEd Data Encoding Monitoring Sheet.xlsx`

**Structure**: 5 sheets named "1" through "5", each with the same column layout. Row 0 is a group header, row 1 is the column header, data starts at row 2. Column headers contain embedded newlines (e.g., `Validated\nLongitude`), so columns are accessed by **position index** rather than name.

**Key column positions** (consistent across all 5 sheets):

| Index | Column |
|---|---|
| 3 | Region |
| 4 | Division |
| 5 | LIS School ID |
| 6 | School Name |
| 7 | Barangay |
| 14 | Findings |
| 15 | Source (validator's chosen source) |
| 16 | Validated Longitude |
| 17 | Validated Latitude |

**Transformations**:
1. Stack all 5 sheets via `pd.concat` with `ignore_index=True`
2. Rename columns by position (not name) to avoid newline issues
3. Filter: keep only rows where `findings` (stripped, lowercased) == `"validated"`
4. Parse `validated_latitude` and `validated_longitude` to numeric, coercing errors to NaN
5. Drop rows failing `has_valid_coords` (null or non-finite lat/lon)
6. Normalize `school_id` via `normalize_school_id` (strip whitespace, remove trailing `.0`)
7. Preserve the `Source` column as `monitoring_chosen_source` (values: "OSMapaaralan", "NSBI", "New coordinates")
8. Tag all rows with `source = "monitoring_validated"`

**Output columns**: `school_id, school_name, latitude, longitude, region, division, barangay, monitoring_chosen_source, source`

**Row count**: 7,727 validated rows with coordinates (from ~11,331 total across all findings categories)

**Missing location columns**: `province` and `municipality` are not present in this source — set to `None`.

### 1.2 Source B — OSMapaaralan (`load_osmapaaralan.py`)

**Raw file**: `osmapaaralan_overpass_turbo_export.geojson`

**Structure**: GeoJSON FeatureCollection with 44,427 features. Geometry types: Polygon (42,193), MultiPolygon (222), Point (2,010), LineString (2). The `ref` property holds the DepEd school ID.

**Transformations**:
1. Parse JSON and iterate over features
2. Skip features where `ref` is null or empty
3. Extract coordinates based on geometry type:
   - **Point**: use coordinates directly `[lon, lat]`
   - **Polygon**: compute centroid of the exterior ring (arithmetic mean of all vertex lon/lat values)
   - **MultiPolygon**: compute centroid of each polygon's exterior ring, then take the mean of those centroids
   - **LineString**: arithmetic mean of all vertex coordinates
4. Resolve `municipality` from multiple OSM address fields in fallback order: `addr:city` → `addr:town` → `addr:municipality` → `addr:village` → `addr:place`
5. Normalize `school_id`, parse lat/lon to numeric, drop invalid coordinates
6. Tag all rows with `source = "osmapaaralan"`

**Centroid method note**: The arithmetic mean of vertices is used rather than a true geometric centroid (area-weighted). For school footprints (typically small, roughly convex polygons), the difference is negligible.

**Output columns**: `school_id, school_name, latitude, longitude, region, province, municipality, barangay, source`

**Row count**: 44,425 (2 features dropped — no valid ref or coords)

**Missing location columns**: `region` and `barangay` are not reliably present in OSM data — set to `None`.

### 1.3 Source C — NSBI 2023-2024 (`load_nsbi.py`)

**Raw file**: `SY 2023-2024 LIST OF SCHOOLS WITH LONGITUDE AND LATITUDE.xlsx`

**Structure**: Single sheet `DB`. Rows 0–4 are title/metadata, row 5 is the header, data starts at row 6. 13 columns.

**Transformations**:
1. Read with `header=5`, all columns as string dtype
2. Rename columns to normalized names (e.g., `LIS SCHOOL ID` → `school_id`, `School Name` → `school_name`)
3. Normalize `school_id`, parse lat/lon to numeric, drop invalid coordinates
4. Tag with `source = "nsbi_2324"`

**Output columns**: `school_id, school_name, latitude, longitude, region, division, province, municipality, barangay, source`

**Row count**: 47,189

**Note**: This source has the most complete administrative metadata of all four sources, which is why it leads the location column priority.

### 1.4 Source D — Geolocation of Public Schools (`load_geolocation.py`)

**Raw file**: `Geolocation of Public Schools_DepEd.xlsx`

**Structure**: Sheet `Geolocations`, header at row 0. 15 columns. Also contains other sheets (`24-2025`, `School ID Mapping`, `Corrected PSIP 3 Loc`, `2023-2024`) — only `Geolocations` is used for coordinates; `School ID Mapping` is used for the crosswalk.

**Transformations**:
1. Read with `header=0`, all columns as string dtype
2. Rename columns (e.g., `School_ID` → `school_id`, `School_Name` → `school_name`; note underscore naming convention differs from NSBI)
3. Normalize `school_id`, parse lat/lon to numeric, drop invalid coordinates
4. Tag with `source = "geolocation_deped"`

**Output columns**: `school_id, school_name, latitude, longitude, region, division, province, municipality, barangay, source`

**Row count**: 47,382

### 1.5 Source E — DRRMS IMRS 2025 (`load_drrms.py`)

**Raw file**: `DRRMS IMRS data 2025.csv`

**Structure**: 27,172 rows, 85 columns. Each row is a disaster/emergency incident report filed by a school official through DepEd's Disaster Risk Reduction Management Service Incident Management Reporting System. This is not a school list — it's a disaster reporting dataset that incidentally contains school coordinates. Schools with multiple disaster reports appear as multiple rows.

**Transformations**:
1. Read CSV with all columns as string dtype
2. Rename columns: `deped school id number` → `school_id`, `name of school or deped facility` → `school_name`, `municipality/city` → `municipality`, `sdo` → `division`
3. Normalize `school_id`, drop rows with null school_id
4. Deduplicate by `school_id`, keeping first occurrence (earliest disaster report)
5. Parse lat/lon to numeric, drop invalid coordinates
6. Normalize region names from DRRMS long format to short format via a mapping (e.g., "REGION V (BICOL REGION)" → "Region V", "CORDILLERA ADMINISTRATIVE REGION (CAR)" → "CAR")
7. Normalize province/municipality/barangay to title case
8. Tag with `source = "drrms_imrs"`

**Region name mapping**: DRRMS uses verbose region names with parenthetical suffixes. A static mapping converts all 18 known variants to the short format used by other sources. Unknown region names are kept as-is (stripped).

**Output columns**: `school_id, school_name, latitude, longitude, region, division, province, municipality, barangay, source`

**Row count**: 16,131 unique schools with coordinates (from 27,172 disaster reports across 16,851 unique school IDs)

**Coordinate quality**: 100% of coordinates fall within the Philippines bounding box — no outliers, no swapped lat/lon. This is notably cleaner than the private school TOSF data (8.7% invalid). Likely because disaster reporters reference their school's known location rather than estimating.

**Sector**: All non-null rows are `sector = PUBLIC`. The 1,111 rows with null sector are also public schools based on their IDs. No private school filtering needed.

## 2. School ID Crosswalk (`build_crosswalk.py`)

DepEd school IDs change over time — most commonly when a school's curricular offering classification changes (e.g., an elementary school begins offering high school and becomes an "integrated school" with a new ID). The crosswalk resolves these changes so that the same physical school is not split across multiple rows.

### 2.1 Layer 1 — Official Mapping

**Source**: "School ID Mapping" sheet in `Geolocation of Public Schools_DepEd.xlsx`

**Structure**: 67,610 rows × 30 columns. Key columns:
- `school_id_2024`: the most recent (canonical) ID
- `BEIS School ID`: an older identifier system
- `old_school_id`, `old_school_id.1`: explicit old→new mappings
- `sy_2005` through `sy_2024`: which ID the school held in each school year (mostly null — only 2,389 rows have any SY data)

**Algorithm**:
1. For each row, designate `school_id_2024` as the canonical ID
2. Collect all distinct IDs from SY columns, `old_school_id` columns, and `BEIS School ID`
3. For each historical ID that differs from the canonical:
   - Record `year_first_seen` and `year_last_seen` (from SY columns; null if from old_school_id/BEIS)
   - Emit a crosswalk entry with `match_method = "official_mapping"`
4. Also emit an identity entry (canonical → canonical) for every canonical ID
5. Deduplicate by `(historical_id, canonical_id)` pair

**Output**: 80,219 entries (67,610 identity + 12,609 non-identity remaps)

**Year data availability**: Of the 12,609 non-identity remaps, only 3,480 have year range data (from SY columns). The remaining 9,129 came from old_school_id or BEIS columns without temporal information.

### 2.2 Layer 2 — Spatial + Name Deduplication

**Purpose**: Catch school IDs that appear in the 4 coordinate sources but are absent from the official mapping. Typically these are OSMapaaralan-specific IDs (e.g., compound IDs like `105596;306832`).

**Algorithm**:
1. Identify "orphan" school IDs — present in at least one source but not in any crosswalk entry (Layer 1)
2. For each orphan with valid coordinates, compute haversine distance to all canonical-ID schools
3. Filter candidates within **100 meters** (`DISTANCE_THRESHOLD_KM = 0.1`)
4. Among spatial candidates, compute name similarity using Python's `SequenceMatcher` ratio
5. Accept the best match if similarity ≥ **0.6** (`NAME_SIMILARITY_THRESHOLD`)
6. Emit with `match_method = "spatial_name"`, no year data

**Output**: 306 orphan IDs evaluated, 114 matched

**Threshold rationale**:
- 100m spatial threshold: schools are fixed physical locations; 100m accounts for centroid approximation differences while avoiding matches across distinct nearby schools
- 0.6 name similarity: accommodates naming variations (e.g., "Conversion ES" ↔ "Conversion Integrated School") while rejecting unrelated co-located schools

### 2.3 Crosswalk Application

After the crosswalk is built, all four source DataFrames have their `school_id` column remapped:
1. Deduplicate the crosswalk by `historical_id` (keep first — Layer 1 takes priority over Layer 2)
2. Build a lookup: `historical_id → canonical_id`
3. Map each source's `school_id` through the lookup; keep original if not in crosswalk

**Remapping counts**:

| Source | IDs Remapped | Context |
|---|---|---|
| OSMapaaralan | 1,731 | Largest — OSM often uses older or compound IDs |
| Geolocation DepEd | 274 | Some schools under BEIS IDs ≠ current LIS IDs |
| NSBI 2023-2024 | 273 | Fewer — most current official list |
| Monitoring | 84 | Smallest — validated schools already flagged by current IDs |

### 2.4 Private School Exclusion from Public Sources

OSMapaaralan's GeoJSON contains school footprints for **both public and private** schools — there is no reliable sector field in the OSM data to distinguish them during loading. Without filtering, 530+ private schools would appear in the public output as duplicate rows (once from OSMapaaralan in the public pipeline, once from the TOSF file in the private pipeline).

**Detection**: Cross-referencing the public and private outputs revealed 530 school IDs appearing in both. 529 of these had `coord_source = osmapaaralan` and `enrollment_status = no_enrollment_reported` (because the enrollment file correctly lists them as private sector). Their names were clearly private schools (e.g., "Sacred Heart School", "St. Mary's Academy").

**Solution**: After crosswalk remapping (Step 1.5), the pipeline collects all known private school IDs from two sources:
1. The TOSF LIS universe (the `SCHOOLS WITHOUT SUBMISSION` sheet — 12,011 private school IDs)
2. The enrollment file filtered to `sector = "Private"` (catches private schools not in the TOSF universe)

Any school ID in this combined private set is removed from all four public source DataFrames.

**Why exclusion runs after remapping, not before**: Some OSMapaaralan entries use old school IDs (e.g., `346004`) that only resolve to a known private school ID (e.g., `407461`) after crosswalk remapping. Excluding before remapping would miss these cases.

**Result**: 538 private school records removed (535 from OSMapaaralan, 1 each from monitoring, NSBI, and geolocation).

**Remaining overlap**: 1 school ID (`400233`) appears in both outputs. This is a genuine DepEd ID collision — "Sungay IS" (public, active) and "St. Thomas Aquinas Learning Center of Vigan City, Inc." (private, active) are different schools that share the same numeric ID across sectors. This is not a pipeline error and is retained as-is.

### 2.4 Impact on School Universe

Before crosswalk: **49,823** unique school IDs across all sources.
After crosswalk: **48,369** unique canonical school IDs.
Reduction: **1,454** IDs folded into existing canonical entries.

These 1,454 IDs were old/alternate identifiers for schools that also appeared under their canonical ID in another source. Without the crosswalk, they would have been separate rows — some with coordinates from only one source, duplicating the same physical school.

**Cross-source merge**: 1,319 cases where an old ID in OSMapaaralan was remapped to a canonical ID in NSBI. This means these schools now correctly receive both OSMapaaralan coordinates (via the priority cascade) and NSBI administrative metadata (via the location fill).

## 2.5 Enrollment-Based Universe Expansion (`load_enrollment.py`)

The four coordinate sources do not capture every operational public school. Cross-referencing with enrollment data revealed schools that have active enrollment but were never included in any geolocation effort.

### 2.5.1 Source

**File**: `SY_2024_2025_School_Level_Data_on_Official_Enrollment.csv`

School-level enrollment data for SY 2024-2025 (the school year that concluded March 2026). Contains 60,095 rows across public, private, and SUCsLUCs sectors.

### 2.5.2 Loading and Filtering

1. Read the CSV with all columns as string dtype
2. Resolve column names via an alias mapping (handles variants like `school_id`, `LIS SCHOOL ID`, `beis_school_id`)
3. Filter to `sector == "Public"` only → 47,972 unique public schools
4. Deduplicate by `school_id`, keep first occurrence
5. Extract available location columns: `region`, `division`, `province`, `municipality`, `barangay`

### 2.5.3 Identifying Missing Schools

Enrollment school IDs are remapped through the crosswalk (enrollment may use historical IDs), then compared against the coordinate universe (48,369 canonical IDs from the four coordinate sources).

**Result**: 562 public schools in enrollment but not in the coordinate universe.

These 562 fall into two categories:

| Category | Count | Description |
|---|---|---|
| Not in crosswalk at all | 19 | Completely new school IDs — likely schools created for SY 2024-2025 that didn't exist when coordinate data was compiled |
| In crosswalk but canonical lacks coords | 543 | The School ID Mapping tab knows about these schools (they have a `school_id_2024` entry), but none of the four coordinate sources have data for them under any historical or canonical ID |

The 543 schools in the second category are administratively registered by DepEd (assigned IDs, tracked in the mapping system) but were never captured by any geolocation effort: not mapped in OSM, not in NSBI, not in the internal Geolocation file, and not flagged for monitoring validation. They exist in the enrollment system because they are operational and enrolling students.

### 2.5.4 Verification

- **0** of the 562 overlap with any school that has coordinates in the final output
- **0** appear in any raw coordinate source under any historical or canonical ID
- After expansion, every public school in the enrollment file is accounted for — either directly in the coordinates table or resolvable via the crosswalk

### 2.5.5 Generalized Design

The enrollment loader (`load_enrollment.py`) is designed to accept any school-level enrollment CSV, not just the SY 2024-2025 file. New enrollment files are added by appending their path to the `ENROLLMENT_FILES` list at the top of the orchestrator script — no code changes required. The alias mapping handles common column name variations across DepEd enrollment exports.

## 3. Coordinate Priority Cascade

For each canonical school ID, coordinates are selected from the **first available** source in priority order:

1. **monitoring_validated** (7,722 schools) — university-validated, highest trust
2. **osmapaaralan** (37,831 schools) — OSM human-validated
3. **nsbi_2324** (2,183 schools) — official but dated
4. **geolocation_deped** (103 schools) — internal office revision
5. **drrms_imrs** (25 schools) — self-reported via disaster incident reports; only source for these schools

**Implementation**: Sources are indexed by `school_id` (deduplicated, first occurrence kept). The cascade iterates in priority order; schools that already have coordinates from a higher-priority source are skipped.

**Lineage tracking per school**:
- `coord_source`: which source provided the final coordinates
- `monitoring_chosen_source`: if from monitoring, which sub-source the validator chose (OSMapaaralan, NSBI, or New coordinates)
- `sources_available`: comma-separated list of all sources that had coordinates for this school; `enrollment_only` for schools known only from enrollment

### 3.5 Enrollment Status Tagging

After the coordinate cascade and location fill, every school is tagged with `enrollment_status`:

- **`active`** (47,891 schools) — school ID found in the SY 2024-2025 enrollment data (public sector)
- **`no_enrollment_reported`** (1,040 schools) — school exists in coordinate sources but has no enrollment record in SY 2024-2025

This tag does not affect coordinates or location columns — it is purely informational. A school with `no_enrollment_reported` may have temporarily ceased operations, merged with another school, or simply not yet reported. Its coordinates remain valid.

The enrollment IDs are remapped through the crosswalk before comparison, so historical ID mismatches do not cause false negatives.

## 4. Location Column Fill

Administrative location columns (`region`, `province`, `municipality`, `barangay`) are filled independently from coordinates, using a separate priority:

1. **nsbi_2324** (47,122 schools) — most complete admin metadata
2. **geolocation_deped** (193 schools)
3. **monitoring_validated** (0 schools — NSBI already covered them)
4. **osmapaaralan** (429 schools)
5. **drrms_imrs** (25 schools) — for schools only in DRRMS
6. **enrollment** (562 schools) — fallback for enrollment-only schools
7. No location data: 95 schools

**Implementation**: For each school, try each source in order. Accept the first source that has at least one non-null location column. Record `location_source` for provenance. For enrollment-only schools (those added in Step 2.5), location columns are filled from the enrollment file after the four coordinate sources have been exhausted. These schools are also tagged with `sources_available = "enrollment_only"` to distinguish them from schools that have coordinate data.

**School name**: Filled separately using the coordinate priority order (monitoring → OSMapaaralan → NSBI → Geolocation). First source with a non-null name wins.

## 5. Validation

### 5.1 Coordinate Completeness

Of 48,426 total schools, 47,864 have coordinates (from the five coordinate sources) and 562 do not (enrollment-only schools). The five coordinate sources cover 100% of their own universe; the 562 gaps exist only because the enrollment expansion added schools that no coordinate source has ever captured.

### 5.2 Cross-Source Discrepancies

Schools appearing in multiple sources are compared pairwise using haversine distance. Schools with >1 km disagreement:

| Source Pair | Schools >1 km Apart |
|---|---|
| monitoring_validated vs osmapaaralan | 245 |
| monitoring_validated vs nsbi_2324 | 2,262 |
| monitoring_validated vs geolocation_deped | 961 |
| osmapaaralan vs nsbi_2324 | 3,332 |
| osmapaaralan vs geolocation_deped | 1,996 |
| nsbi_2324 vs geolocation_deped | 1,445 |

The highest discrepancy is between OSMapaaralan and NSBI (3,332 schools), which validates the motivation for the monitoring effort.

## 6. Output Formats

### 6.1 Parquet Files
- `public_school_coordinates.parquet` — 48,426 rows, 13 columns
- `public_school_id_crosswalk.parquet` — 80,385 rows, 5 columns

### 6.2 CSV
- `public_school_coordinates.csv` — same content as parquet, for universal access

### 6.3 Excel Workbook
- `public_school_coordinates.xlsx` — three sheets:
  - **Metadata**: pipeline description, source priorities, summary statistics, timestamp
  - **Unified School Coordinates**: the canonical coordinates table
  - **School ID Crosswalk**: historical-to-canonical ID mapping

### 6.4 Build Report
- `output/build_public_report.txt` — text summary of all statistics, written each run

## 7. Shared Utilities (`utils.py`)

### `normalize_school_id(value)`
Handles both pandas Series and scalar values. Strips whitespace and removes trailing `.0` (common when Excel reads numeric IDs as floats). Returns `None` for empty/null inputs.

### `has_valid_coords(df)`
Boolean mask: non-null AND finite for both latitude and longitude. Used by all loaders to drop rows with missing or corrupt coordinates.

### `haversine_km(lat1, lon1, lat2, lon2)`
Vectorized (numpy) haversine formula. Returns great-circle distance in kilometers. Used for cross-source discrepancy checks and Layer 2 spatial matching.

## 8. Known Limitations

1. **Centroid approximation**: OSMapaaralan polygon centroids use arithmetic mean of vertices, not area-weighted geometric centroids. Acceptable for small school footprints.
2. **Layer 2 matching is conservative**: The 100m + 0.6 name similarity thresholds intentionally favor precision over recall. Some legitimate ID changes may be missed if the school name changed significantly or the centroid drifted beyond 100m.
3. **School ID Mapping coverage**: The official mapping tab has SY data for only 2,389 of 67,610 rows. Most crosswalk entries rely on the `old_school_id` / `BEIS School ID` columns without temporal context.
4. **Schools that split or merge**: The crosswalk does not handle cases where one school splits into two or two schools merge. These remain as separate entries.
5. **Duplicate school IDs within a source**: When a source has multiple rows for the same school_id (after remapping), `drop_duplicates(keep="first")` is applied. The "first" row depends on the original row order in the source file.
6. **358 schools have no location data**: These are schools present only in OSMapaaralan with no matching NSBI/Geolocation/Monitoring/Enrollment entry, and where OSMapaaralan itself lacks address properties.
7. **563 enrollment-only schools have no coordinates**: These schools are operationally active (have enrollment data) but were never captured by any of the four geolocation sources. Their coordinates remain null until a future geolocation effort covers them.
8. **SUCsLUCs (180 schools) are excluded**: The enrollment file contains 180 State Universities/Colleges and Local Universities/Colleges, a third sector not covered by either the public or private pipeline. These are not included in any output.
9. **1 cross-sector ID collision**: School ID `400233` is assigned to both a public school ("Sungay IS") and a private school ("St. Thomas Aquinas Learning Center of Vigan City, Inc."). Both are retained in their respective outputs. This is a DepEd administrative artifact, not a pipeline error.
