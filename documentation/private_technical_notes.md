# Technical Notes — Private School Coordinates Pipeline

Comprehensive record of all processing and transformation decisions applied to the Private School Seats and TOSF data collection to produce a canonical private school coordinates table.

## 1. Source Ingestion & Normalization

### 1.1 School Universe — SCHOOLS WITHOUT SUBMISSION Sheet

**Raw file**: `Private School Seats and TOSF ao 2025Oct27.xlsx`, sheet `SCHOOLS WITHOUT SUBMISSION`

**Structure**: Header at row index 5, 12,011 data rows, 17 columns. This is the LIS master list of private schools as of September 2025 — it includes all private schools regardless of whether they submitted the Google Form.

**Column mapping**:

| Raw Column | Normalized Column |
|---|---|
| `beis_school_id` | `school_id` |
| `School Name` | `school_name` |
| `Region` | `region` |
| `Division` | `division` |
| `Province` | `province` |
| `Municipality` | `municipality` |
| `Barangay` | `barangay` |
| `Has the school Submitted the GForm?` | `submitted` (boolean) |

**Transformations**:
1. Read with `header=5`, all columns as string dtype
2. Rename columns to normalized names
3. Normalize `school_id` via `normalize_school_id` (strip whitespace, remove trailing `.0`)
4. Drop rows with null school_id (none found — all 12,011 are valid)
5. Parse `submitted` flag: "Yes" → `True`, everything else → `False`

**Output**: 12,011 rows, all with unique school IDs. No deduplication needed.

**Unused columns**: `District`, `street_address`, `school_head_name`, `school_head_position_name`, `Legislative District`, `Sector`, `School_subclassification`, `Curricular_offering_classification`, `Rural/Urban Classification` — available in the raw file but not carried into the pipeline output.

### 1.2 Coordinates — RAW DATA Sheet

**Raw file**: Same file, sheet `RAW DATA`

**Structure**: Header at row index 7 (rows 0–6 are title/metadata/group headers), 10,365 data rows, 46 columns. Collected via Google Forms — each row is a school's self-reported submission.

**Column mapping** (used columns only):

| Raw Column | Normalized Column |
|---|---|
| `Validated School Data` | `school_id` (primary) |
| `BEIS School ID` | `school_id` (fallback if Validated is null) |
| `Latitude` | `latitude` |
| `Longitude` | `longitude` |
| `ESC` | `esc_participating` |
| `SHS VP` | `shsvp_participating` |
| `JDVP` | `jdvp_participating` |

**Transformations**:
1. Read with `header=7`, all columns as string dtype
2. Canonical school ID: use `Validated School Data`, fall back to `BEIS School ID` if null. These match for 10,324 of 10,365 rows; 41 were corrected by DepEd.
3. Normalize `school_id`
4. Deduplicate by `school_id`, keeping first occurrence (10,365 → 9,632 unique schools)
5. Parse `Latitude` and `Longitude` to numeric, coercing errors to NaN
6. Parse GASTPE flags: "1" → 1, else → 0

**Output**: 9,632 unique school submissions with raw coordinates (before cleaning).

**Unused columns**: `Email Address`, `School Name` (from RAW DATA — the universe sheet's name is preferred), `Street Address`, `Legislative District`, `Province`, `City or Municipality`, `Barangay` (from RAW DATA — the universe sheet's admin metadata is preferred), grade-level seat counts (Kinder–Grade 12), TOSF columns (Grade 1.1–Grade 12.1).

## 2. Coordinate Cleaning

Self-reported coordinates require cleaning. Three sequential passes are applied:

### 2.1 Pass 1 — Fix Swapped Lat/Lon

**Condition**: The value in the longitude column falls within the Philippines latitude range [4.5, 21.5] AND the value in the latitude column falls within the Philippines longitude range [116, 127], AND the original values are NOT already valid (i.e., lat not in [4.5, 21.5] or lon not in [116, 127]).

**Action**: Swap lat ↔ lon.

**Result**: 105 schools fixed.

**Rationale**: Google Forms does not enforce coordinate order. Some respondents entered longitude in the latitude field and vice versa. Since the Philippines has non-overlapping latitude and longitude ranges (lat ~5–21, lon ~117–127), swapped values are unambiguously detectable.

### 2.2 Pass 2 — Reject Invalid Coordinates

**Condition** (any of):
- Latitude or longitude is null or NaN
- Latitude or longitude is non-finite (inf)
- |latitude| > 90 or |longitude| > 180 (impossible on Earth)
- Latitude or longitude is exactly 0 (default/placeholder values)

**Action**: Set both coordinates to NaN. Mark `coord_status = "no_coords"`, `coord_rejection_reason = "invalid"`.

**Result**: 505 schools rejected.

**Examples of rejected values**: `12106494` (likely entered without decimal point), `1457929`, `0`, entries that failed numeric parsing.

### 2.3 Pass 3 — Reject Out-of-Philippines Bounds

**Condition**: After passes 1–2, coordinates that are numerically valid but fall outside the Philippines bounding box:
- Latitude not in [4.5, 21.5]
- Longitude not in [116.0, 127.0]

**Action**: Set both coordinates to NaN. Mark `coord_status = "no_coords"`, `coord_rejection_reason = "out_of_bounds"`.

**Result**: 208 schools rejected.

**Bounding box rationale**: The box [4.5–21.5, 116–127] covers all Philippine territory from Tawi-Tawi/Sitangkai in the south (~4.8°N) to Batanes in the north (~20.9°N), and from the western Palawan coast (~116.9°E) to the eastern Mindanao coast (~126.6°E). The 0.5° padding accommodates minor GPS inaccuracies.

### 2.4 Cleaning Summary

| Category | Count | % of Submissions |
|---|---|---|
| Valid (no changes needed) | 8,809 | 91.5% |
| Fixed swap | 105 | 1.1% |
| Rejected invalid | 505 | 5.2% |
| Rejected out-of-bounds | 208 | 2.2% |
| **Total submissions** | **9,632** | |

After cleaning: **8,914 schools with usable coordinates** (8,809 valid + 105 fixed swaps).

### 2.5 Cleaning Pass Order Matters

The passes are ordered deliberately:
1. **Swap first** — recovers coordinates that would otherwise be rejected as out-of-bounds
2. **Invalid second** — removes values that are impossible on Earth (no point checking bounds)
3. **Out-of-bounds last** — catches plausible but incorrect coordinates (e.g., lat=14, lon=15 is valid on Earth but not in the Philippines)

## 3. Merge: Universe + Coordinates

Left join: universe (12,011 schools) ← cleaned coordinates (9,632 submissions → 8,914 with valid coords).

**Schools without coordinates** (3,097 total):
- `no_submission` (2,385): school exists in LIS but did not submit the Google Form
- `invalid` (504): submitted but coordinates were rejected as invalid
- `out_of_bounds` (208): submitted but coordinates fell outside PH bounds

**Location columns**: Sourced exclusively from the universe sheet (LIS official metadata), not from the self-reported RAW DATA. The LIS names and admin fields are standardized; the Google Form responses have inconsistent formatting (e.g., "Province of Laguna" vs "Laguna" vs "LAGUNA").

**School name**: From the universe sheet only — the LIS official name.

**GASTPE flags**: Joined from RAW DATA where available (submitted schools only). Non-submitting schools receive 0 for all three flags.

## 3.5 Enrollment-Based Universe Expansion

The LIS master list (September 2025) may not capture every operational private school — schools may have opened or been reclassified between the LIS extract date and the enrollment reporting period.

### 3.5.1 Process

1. Load enrollment CSV, filter to `sector == "Private"`, deduplicate by school ID
2. Compare against the LIS universe (12,011 schools)
3. Add missing schools with `coord_status = "no_coords"`, `coord_rejection_reason = "not_in_lis"`
4. Location columns sourced from the enrollment file; GASTPE flags set to 0

**Result**: 157 private schools added from SY 2024-2025 enrollment data. Final universe: 12,168 schools.

### 3.5.2 The 157 Schools

These are private schools that have reported enrollment in SY 2024-2025 but do not appear in the September 2025 LIS master list used for the TOSF data collection. They have no coordinates because they were never part of the TOSF Google Form exercise. Their location columns come from the enrollment file.

## 3.6 Enrollment Status Tagging

Every school receives an `enrollment_status` tag by checking whether its ID appears in the SY 2024-2025 enrollment data (private sector):

- **`active`** (11,940 schools) — has reported enrollment
- **`no_enrollment_reported`** (228 schools) — in LIS/TOSF but no enrollment in SY 2024-2025

The 228 schools with no reported enrollment are retained with their coordinates (if any) intact. They may have temporarily ceased operations, merged, or simply not yet reported. The tag is informational — it does not affect coordinates or location columns.

## 4. Validation Results

### 4.1 Coordinate Coverage

| Metric | Count | % |
|---|---|---|
| Total private schools | 12,168 | 100% |
| With coordinates | 8,914 | 73.3% |
| Without coordinates | 3,254 | 26.7% |

### 4.2 Regional Coverage

Coverage varies significantly by region. Highest: Region I (90%), Region XII (88%), CARAGA (87%). Lowest: BARMM (42%), NCR (61%).

### 4.3 GASTPE Participation

Among submitting schools:
- ESC: 3,696 schools
- SHS VP: 3,995 schools
- JDVP: 585 schools

## 5. Output Formats

### 5.1 Parquet + CSV
- `private_school_coordinates.parquet` — 12,168 rows, 15 columns
- `private_school_coordinates.csv` — same content

### 5.2 Excel Workbook
- `private_school_coordinates.xlsx` — two sheets:
  - **Metadata**: pipeline description, source info, cleaning thresholds, GASTPE flag definitions
  - **Private School Coordinates**: the canonical table

### 5.3 Build Report
- `output/build_private_report.txt` — text summary with regional breakdown

## 6. Differences from Public School Pipeline

| Aspect | Public Schools | Private Schools |
|---|---|---|
| Sources | 4 (monitoring, OSM, NSBI, Geolocation) | 1 (TOSF Google Form) |
| Core challenge | Source selection (priority cascade) | Coordinate quality (cleaning) |
| Crosswalk | Yes (historical ID changes) | No (single source, no ID history) |
| Coordinate validation | Human-validated (monitoring, OSM) | Self-reported (no validation layer) |
| Universe size | 48,369 canonical schools | 12,011 schools |
| Coordinate coverage | 100% | 74.2% |
| Lineage tracking | `coord_source` (which of 4 sources) | `coord_status` (valid/fixed/rejected) |

## 7. Known Limitations

1. **Self-reported coordinates have no validation layer** — even the 8,914 "valid" coordinates may be inaccurate (e.g., pointing to the wrong building, the school head's home, or a general municipality centroid). No cross-source verification is possible with a single source.
2. **Bounding box is a coarse filter** — a coordinate that falls within the Philippines box but is still wrong (e.g., correct province but wrong city) will pass cleaning undetected.
3. **GASTPE flags are only available for submitting schools** — non-submitting schools receive 0, which is indistinguishable from "submitted and does not participate". The `coord_status` column can be used to distinguish (no_coords + no_submission = did not submit).
4. **Universe may undercount** — the LIS list is from September 2025 and may not include very new schools or exclude recently closed ones.
5. **Deduplication keeps first submission** — if a school submitted twice with different coordinates, only the first is retained. There is no way to determine which is more accurate.
