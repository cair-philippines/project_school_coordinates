# School ID Crosswalk — 7-Digit Reconciliation

**Status:** Implemented 2026-04-17. Outputs regenerated. Downstream consumers must re-read parquets.

This document traces the full arc of a bug in the school ID crosswalk, from the external brief that motivated the investigation to the implemented fix and measured results. It exists so that future readers can see *why* the crosswalk behaves the way it does — the algorithm is now non-obvious without context.

## Contents

1. [The motivating brief (from a downstream project)](#1-the-motivating-brief-from-a-downstream-project)
2. [Additional findings in project_coordinates](#2-additional-findings-in-project_coordinates)
3. [What the brief understated — three additions](#3-what-the-brief-understated--three-additions)
4. [Implementation](#4-implementation)
5. [Results: pre vs post comparison](#5-results-pre-vs-post-comparison)
6. [Downstream implications](#6-downstream-implications)
7. [Residual items](#7-residual-items)

---

## 1. The motivating brief (from a downstream project)

On 2026-04-16, a downstream project that builds an ML model for predicting Grade 6 → Grade 7 school transfers sent a brief to the maintainer of this repository, reporting that the school ID crosswalk was producing canonical IDs in a format that no longer exists in any current DepEd system. The original brief lives in that project's documentation directory.

### The problem they surfaced

`modules/build_crosswalk.py` assigns canonical school IDs by reading the `school_id_2024` column of the "School ID Mapping" tab in `data/bronze/frozen/Geolocation of Public Schools_DepEd.xlsx`.

In 2024, DepEd temporarily assigned 7-digit school IDs to ~7,000 schools by prepending `1` to their existing 6-digit IDs. By SY 2024-25, DepEd reverted to the standard 6-digit format. But the Excel's `school_id_2024` column still carries the transient 7-digit values for those schools.

| Finding (from the brief) | Number |
|---|---:|
| Schools with 7-digit `school_id_2024` | 7,181 / 67,610 (10.6%) |
| Leading digit of 7-digit IDs | `1` in 7,178 cases (99.96%) |
| 7-digit IDs found in 2024-25 enrollment | **0** |
| Stripped to 6-digit (drop leading `1`) → found in 2024-25 enrollment | 7,089 (98.7%) |
| Unresolved after stripping | 92 |

The Excel contradicts itself: the same tab has both `school_id_2024` (complete, 7-digit in these cases) and `sy_2024` (sparse, all 6-digit). Where both exist, 1,063 rows disagree.

### Downstream impact they described

Any project using the crosswalk to join by canonical school ID will:
- Fail to join against 6-digit sources (tuition files, enrollment data, ESC beneficiary records)
- Potentially create duplicate school entities (same school under both its 6-digit and 7-digit IDs)
- Silently drop or miscount records for ~7,000 schools

This was **blocking new feature-table builds in the downstream school-transfer prediction project**.

### Fix they recommended

Three changes in `build_crosswalk.py`:

1. **Reconcile 7-digit canonicals against 2024-25 enrollment.** When `school_id_2024` is 7 digits starting with `1`, strip the leading digit and verify the 6-digit candidate exists in the enrollment ID set; adopt the 6-digit as canonical if so.
2. **Post-build validation** warning if any canonical_id is not 6 digits.
3. **Extend `SY_COLS`** to include `sy_2025` when the Excel is next updated.

---

## 2. Additional findings in project_coordinates

Before accepting the brief as-is, we inspected our outputs against the claim.

```
Current crosswalk (pre-fix):
  Rows:                 80,357
  Unique canonical_id:  67,610
  Canonicals with 6 digits: 63,697
  Canonicals with 7 digits: 16,660   ← 20.7% of entries

Current public_school_coordinates.parquet:
  Total rows:   48,436
  6-digit IDs:  48,062
  7-digit IDs:  374 (372 start with '1')
```

Two findings not in the brief:

### 2a. The 7-digit format can become a historical ID

The brief's fix changes what `canonical` equals for a row but does **not** register the transient 7-digit as a historical ID pointing to the new 6-digit canonical. If any data source still contains `"1502581"`, `remap_source()` has no translation available and passes the stale value through unchanged.

### 2b. Hidden duplicates in the output

Of the 374 schools in the current output with 7-digit IDs, **236 have their 6-digit stripped form already existing as a separate row** in the same parquet. The same physical school is represented twice — once as `"1502581"` and once as `"502581"` — because the crosswalk's inconsistent mapping (Layer 1 row iteration order) produced different remap decisions across sources.

If the brief's naive stripping were applied to the crosswalk alone, those 236 cases would either create literal duplicate `school_id` values in the parquet or silently lose one record's data via `drop_duplicates(keep="first")`.

---

## 3. What the brief understated — three additions

We extended the brief's plan with three additional changes:

### Addition A — Emit the 7-digit as a historical ID

When the crosswalk reconciles `"1502581"` → canonical `"502581"`, also emit `(1502581 → 502581)` as a historical mapping. This lets `remap_source()` translate any stale 7-digit value in any source (not just DepEd's Excel) back to the canonical form.

### Addition B — Merge logic for intra-source duplicates

After the crosswalk fix applies, a single source (e.g. OSMapaaralan) may contain *both* `"1502581"` and `"502581"` as separate rows that now remap to the same canonical. Naive `drop_duplicates(keep="first")` picks arbitrarily. We added a `_consolidate_duplicates()` helper that prefers:

1. Rows with valid latitude + longitude
2. Rows with a non-empty school name
3. Stable first-wins for the remainder

This runs inside `remap_source()` immediately after the ID remap, before downstream code sees the frame.

### Addition C — Hold off extending `SY_COLS`

The brief recommends `range(2005, 2026)` pre-emptively. We deferred this: `pd.read_excel` silently tolerates a missing column, and adding it before the raw file changes risks obscuring a future bug. This should be flipped when the Excel is refreshed.

---

## 4. Implementation

Three files changed: `modules/build_crosswalk.py` (bulk of the work), `scripts/build_coordinates.py` (plumb `enrollment_path`, unpack new return), `modules/load_enrollment.py` (two call sites of `remap_source()` updated for the new return signature).

### 4a. `_build_layer1(project_root, enrollment_path=None)`

New optional parameter. At function entry, load enrollment IDs via `_load_enrollment_ids()`.

Inside the per-row loop, replace the one-line canonical assignment with:

```python
raw_canonical = normalize_school_id(row.get("school_id_2024"))
if not raw_canonical:
    continue

transient_7digit = None
if len(raw_canonical) == 7 and raw_canonical.startswith("1"):
    candidate = raw_canonical[1:]
    if candidate in enrollment_ids:
        canonical = candidate
        transient_7digit = raw_canonical
        reconciled_7digit += 1
    else:
        unresolved_7digit.append(raw_canonical)
        canonical = raw_canonical
else:
    canonical = raw_canonical

historical_ids = {}

# Emit the transient 7-digit form as a historical ID (Addition A)
if transient_7digit and transient_7digit != canonical:
    historical_ids[transient_7digit] = {"first": 2024, "last": 2024}
```

### 4b. Post-build validation in `build()`

After concatenating Layer 1 and Layer 2:

```python
non_6 = (crosswalk["canonical_id"].str.len() != 6).sum()
if non_6 > 0:
    length_dist = crosswalk["canonical_id"].str.len().value_counts().sort_index().to_dict()
    print(f"  WARNING: {non_6:,} crosswalk entries have non-6-digit canonicals")
    print(f"  Canonical length distribution: {length_dist}")
```

### 4c. `_consolidate_duplicates()` helper (Addition B)

```python
def _consolidate_duplicates(df):
    if not df.duplicated(subset="school_id", keep=False).any():
        return df, 0

    work = df.copy()
    sort_keys, ascending = [], []

    if "latitude" in work.columns and "longitude" in work.columns:
        work["_has_coords"] = work["latitude"].notna() & work["longitude"].notna()
        sort_keys.append("_has_coords"); ascending.append(False)
    if "school_name" in work.columns:
        names = work["school_name"].astype(str).str.strip()
        work["_has_name"] = work["school_name"].notna() & (names != "") & (names != "None")
        sort_keys.append("_has_name"); ascending.append(False)

    if sort_keys:
        work = work.sort_values(sort_keys, ascending=ascending, kind="mergesort")

    before = len(work)
    work = work.drop_duplicates(subset="school_id", keep="first")
    work = work.drop(columns=[c for c in ("_has_coords", "_has_name") if c in work.columns])
    return work.reset_index(drop=True), before - len(work)
```

### 4d. `remap_source()` return signature change

Was `(df, remapped_count)`; now `(df, remapped_count, merged_count)`. Callers updated:

| Caller | File |
|---|---|
| `build_and_apply_crosswalk()` | `scripts/build_coordinates.py:101` |
| `find_missing()` | `modules/load_enrollment.py:169` |
| `get_enrollment_ids()` | `modules/load_enrollment.py:199` |

### 4e. `build()` signature change

Was `build(project_root, sources)`; now `build(project_root, sources, enrollment_path=None)`. The new parameter is optional; callers without it retain pre-fix behavior (no 7-digit reconciliation).

In `scripts/build_coordinates.py`, the path is drawn from the existing `ENROLLMENT_FILES` list:

```python
enrollment_path = next(
    (str(p) for p in ENROLLMENT_FILES if p.exists()), None
)
crosswalk = build_crosswalk.build(root, sources, enrollment_path=enrollment_path)
```

---

## 5. Results: pre vs post comparison

Pipeline ran cleanly against fresh inputs on 2026-04-17. Selected stdout highlights:

```
Loaded 60,129 enrollment IDs for canonical reconciliation
Layer 1 (official mapping): 71,685 entries (71,413 unique historical IDs)
Reconciled 7-digit canonicals to 6-digit: 7,120
WARNING: 58 7-digit IDs could not be reconciled against 2024-25 enrollment

Remapping source IDs to canonical...
  monitoring_validated: 45 IDs remapped, 12 merged
  osmapaaralan:       1,799 IDs remapped, 390 merged
  nsbi_2324:            208 IDs remapped, 99 merged
  geolocation_deped:    209 IDs remapped, 100 merged
  drrms_imrs:            89 IDs remapped, 24 merged
```

### 5a. Crosswalk

| Metric | Pre | Post | Δ |
|---|---:|---:|---:|
| Total entries | 80,357 | 71,822 | −8,535 |
| Unique canonical_id | 67,610 | 60,578 | −7,032 |
| Unique historical_id | 71,551 | 71,550 | −1 |
| Canonicals — 6-digit | 63,697 | 71,689 | +7,992 |
| Canonicals — 7-digit | 16,660 | **133** | −16,527 |
| New 7-digit → 6-digit historical entries | — | 7,153 | — |

The 7,032-school drop in unique canonicals reflects the Excel representing the same physical school as both `1502581` and `502581` in different rows. These now consolidate to a single canonical entity. 133 unresolved 7-digit canonicals remain: 58 from Layer 1 (schools with no 2024-25 enrollment, likely closed/merged) plus 75 edge cases propagating through Layer 2.

### 5b. Public coordinates output

| Metric | Pre | Post | Δ |
|---|---:|---:|---:|
| Total rows | 48,436 | 48,140 | −296 |
| 6-digit school_ids | 48,062 | 48,128 | +66 |
| 7-digit school_ids | 374 | **12** | −362 |
| Shadow duplicates (7-digit with existing 6-digit twin) | 236 | **1** | −235 |
| Literal duplicate school_id rows | 0 | 0 | unchanged |

### 5c. Quality columns

| Column / value | Pre | Post | Δ | Reading |
|---|---:|---:|---:|---|
| `psgc_match` | 42,474 | 42,527 | +53 | More schools validate cleanly with consolidated IDs |
| `psgc_mismatch` | 4,655 | 4,666 | +11 | Minor |
| `psgc_no_validation` | 1,307 | **947** | −360 | Previously-7-digit schools now match the PSGC crosswalk and become validatable |
| `coord_status=suspect` | 1,285 | 1,295 | +10 | Equivalent |
| `coord_rejection_reason=wrong_municipality` | 1,178 | 1,189 | +11 | Equivalent |
| `enrollment_status=active` | 47,891 | 47,857 | −34 | Row consolidation |
| `enrollment_status=no_enrollment_reported` | 545 | **283** | −262 | Previously-phantom rows (same school counted twice, one without enrollment) collapsed into one |

### 5d. coord_source redistribution

| Source | Pre | Post | Δ |
|---|---:|---:|---:|
| osmapaaralan | 37,848 | 37,597 | −251 |
| monitoring_validated | 7,722 | 7,714 | −8 |
| nsbi_2324 | 2,176 | 2,140 | −36 |
| geolocation_deped | 103 | 102 | −1 |
| drrms_imrs | 25 | 25 | 0 |
| (none) | 562 | 562 | 0 |

All changes are consistent with duplicate consolidation; no source added or lost coverage.

### 5e. ID set delta

- **362 IDs only in PRE** — all 7-digit starting with `1`; collapsed into their 6-digit twins (expected)
- **66 IDs only in POST** — schools newly surfaced as 6-digit canonicals that were previously hidden under a 7-digit alias
- **48,074 IDs in both** — unchanged identity

---

## 6. Downstream implications

Every project that consumes `public_school_coordinates.parquet` or `public_school_id_crosswalk.parquet` and joins on `school_id` is affected.

| Downstream project | What breaks until re-read | What improves |
|---|---|---|
| School-transfer prediction (ML modeling) | Any cached join keyed on old 7-digit canonicals | The blocker is resolved — joins against 6-digit enrollment, tuition, and ESC beneficiary data now succeed |
| School-to-school connectivity network (road-distance matrix) | Distance-matrix index keyed on old school_ids | Consolidated school identities; fewer phantom nodes |
| ESC program and decongestion policy simulation | Any feature table built against the prior parquet | Cleaner flow aggregations across origin/destination schools |
| School outcome prediction (conditional expectation model) | ML model inputs keyed on old school_ids | Reduced silent record drops during joins |
| **Piring** (this repo's school-locator web app) | Any bookmark using a now-stale 7-digit URL 404s | Fewer duplicate cards in search/filter; `school_id` display is consistently 6-digit |

The change is **backwards-incompatible** for any cached artifact. Communicate before rebuilds.

---

## 7. Residual items

1. **12 unresolved 7-digit IDs** remain in the public coords output. All are OSMapaaralan-sourced private schools (Montessori, Christian Academy, Notre Dame, etc.) that aren't in the TOSF private-school universe or private-sector enrollment, so the existing private-ID filter doesn't catch them. This is a separate concern — private-school leakage, not ID-format — and should be tackled by extending `_load_known_private_ids()` with fuzzy name matching.
2. **58 unresolved 7-digit canonicals** in Layer 1 were logged during the run. These are schools with no entry in 2024-25 enrollment — most likely closed, merged, or renamed. They remain 7-digit in the crosswalk pending manual review.
3. **`SY_COLS` extension to `sy_2025`** is deferred. Flip it when DepEd refreshes the Excel with a `sy_2025` column.
4. **Cloud Run deployment of Piring** needs `prepare_deploy.sh` + redeploy to pick up the new parquets.

---

## Related documentation

- [Pipeline Plan](pipeline_plan.md) — overall public pipeline design
- [Technical Notes](technical_notes.md) — crosswalk algorithm details
- [Duplication Audit](duplication_audit.md) — the "236 systematic X/1X ID pairs" referenced there are precisely the duplicates this fix resolves
