# Public School Coordinates: Duplication Audit Report

**Dataset:** `data/gold/public_school_coordinates.parquet`
**Records:** 48,436 rows, 32 columns
**Date:** 2026-03-21

---

## Audit Summary

| Check | Description | Flags | Priority |
|-------|-------------|-------|----------|
| 1 | Duplicate school IDs | **0** | — |
| 2a | Exact same name, same barangay | **25 pairs** (50 rows) | Highest |
| 2b | Exact same name, same municipality, different barangay | **25 pairs** (49 rows) | High |
| 2c | Exact same name, same province, different municipality | **4,431 rows** (1,007 names) | Low (expected) |
| 2d | Exact same name, same region, different province | **3,057 rows** (1,025 names) | Low (expected) |
| 3 | Near-identical names within same municipality | **6 pairs** (12 rows) | Highest |
| 4 | Null/blank school names | **3 rows** | High |
| 5 | X / 1X ID pairs (XXXXXX vs 1XXXXXX) | **236 pairs** | Medium |

**Actionable items (high priority):** Checks 2a (25 pairs), 3 (6 pairs), 4 (3 nulls), and a subset of Check 5 (81 same-name pairs).

Checks 2c/2d are expected in the Philippines — barangay names like San Isidro, San Jose, and San Vicente repeat across municipalities and provinces, and schools are named after their barangay.

---

## Methodology and Thresholds

### Check 1: Duplicate School IDs

- **Method:** Exact match on the `school_id` column. Any ID appearing more than once is flagged.
- **Threshold:** Count > 1.

### Check 2: Exact Duplicate School Names

- **Method:** Exact string match on `school_name`, grouped by geographic scope.
- **Geographic scoping hierarchy** (most to least suspicious):
  - **2a:** Same `school_name` + same `barangay` + same `municipality` + same `province` + same `region`
  - **2b:** Same `school_name` + same `municipality` + different `barangay`
  - **2c:** Same `school_name` + same `province` + different `municipality`
  - **2d:** Same `school_name` + same `region` + different `province`
- **Cross-region matches:** Not flagged unless a School ID conflict also exists.
- **Null handling:** Schools with null names are excluded from name-based checks and flagged separately in Check 4.

### Check 3: Near-Identical Name Matching

- **Scope:** Within the same municipality (to keep computation tractable on 48K rows).
- **Normalization steps** (applied in order):
  1. Convert to lowercase
  2. Expand abbreviations: `es` → `elementary school`, `ps` → `primary school`, `is` → `integrated school`, `nhs` → `national high school`, `shs` → `senior high school`, `st.` → `saint`, `sta.` → `santa`, `sto.` → `santo`
  3. Remove all punctuation (periods, commas, hyphens, parentheses)
  4. Collapse multiple spaces to single space
  5. Strip leading/trailing whitespace
- **Match rule:** Two schools in the same municipality whose normalized names are identical but original names differ are flagged.

### Check 4: Null/Blank School Names

- **Method:** Flag any row where `school_name` is null, empty string, or the literal string `"None"`.

### Check 5: XXXXXX vs 1XXXXXX Pattern

- **Method:** For each 6-digit `school_id`, check if a 7-digit ID formed by prepending `"1"` also exists. Conversely, for each 7-digit ID starting with `"1"`, check if the 6-digit suffix exists.
- **Sub-classification:** Same-name pairs (identical `school_name` on both IDs) vs different-name pairs.

---

## Findings

### CHECK 1: Duplicate School IDs

**Result: CLEAN.** No `school_id` appears more than once in the dataset.

---

### CHECK 2a: Same Name, Same Barangay — 25 pairs, 50 rows

> **Highest suspicion.** Two different school IDs point to schools with the exact same name in the exact same barangay. In the Philippines, there should only be one school of a given name in a single barangay — so having two entries almost certainly means the same physical school was captured under two different IDs from two different data sources.

**How this happens:** OSMapaaralan mapped a school using one DepEd school ID (from the `ref` tag). The monitoring team or NSBI used a different ID — often because the school was reclassified (e.g., from elementary to integrated) and received a new ID, but the old ID persists in one source. The crosswalk didn't catch the relationship because neither ID was flagged as historical in the School ID Mapping tab.

#### Representative examples

**Old ID + new ID (most common pattern):**

| school_id | school_name | barangay | municipality | coord_source |
|-----------|-------------|----------|--------------|--------------|
| 107857 | Amadeo Integrated School | BARANGAY I (POB.) | AMADEO | osmapaaralan |
| 301166 | Amadeo Integrated School | BARANGAY I (POB.) | AMADEO | osmapaaralan |

> This school was originally elementary (`107857`), then became integrated and got new ID `301166`. Both IDs were mapped in OSM, creating two entries for one school.

**Different data sources captured the same school:**

| school_id | school_name | barangay | municipality | coord_source |
|-----------|-------------|----------|--------------|--------------|
| 114521 | Balogo Elementary School | BALOGO | CITY OF SORSOGON | osmapaaralan |
| 114553 | Balogo Elementary School | BALOGO | CITY OF SORSOGON | monitoring_validated |

> Same school, same barangay, but OSMapaaralan used one ID and the monitoring team used another. Neither was flagged as historical in the crosswalk.

**Both from the same source (data entry error):**

| school_id | school_name | barangay | municipality | coord_source |
|-----------|-------------|----------|--------------|--------------|
| 133593 | Cadayonan PS | CADAYONAN | BAYANG | nsbi_2324 |
| 133679 | Cadayonan PS | CADAYONAN | BAYANG | nsbi_2324 |

> Unusual — both IDs come from NSBI, meaning the official school list itself has two entries for the same school. Likely a data entry error in the NSBI system.

**No geographic data (possibly private schools):**

| school_id | school_name | barangay | municipality | coord_source |
|-----------|-------------|----------|--------------|--------------|
| 401100 | Holy Child Academy | *(blank)* | *(blank)* | osmapaaralan |
| 407501 | Holy Child Academy | *(blank)* | *(blank)* | osmapaaralan |

> Both have `4xxxxx` IDs (private school range) and completely blank location data. These may be private schools that survived the private-school exclusion filter because their IDs weren't in the TOSF or enrollment files.

#### Full list

| school_id | school_name | region | province | municipality | barangay | coord_source |
|-----------|-------------|--------|----------|-------------|----------|-------------|
| 120120 | Ali-is Integrated School | NIR | NEGROS ORIENTAL | CITY OF BAYAWAN (TULONG) | ALI-IS | osmapaaralan |
| 501131 | Ali-is Integrated School | NIR | NEGROS ORIENTAL | CITY OF BAYAWAN (TULONG) | ALI-IS | monitoring_validated |
| 107857 | Amadeo Integrated School | Region IV-A | CAVITE | AMADEO | BARANGAY I (POB.) | osmapaaralan |
| 301166 | Amadeo Integrated School | Region IV-A | CAVITE | AMADEO | BARANGAY I (POB.) | osmapaaralan |
| 109393 | Balanti Elementary School | Region IV-A | RIZAL | CAINTA | SAN ISIDRO | monitoring_validated |
| 109394 | Balanti Elementary School | Region IV-A | RIZAL | CAINTA | SAN ISIDRO | osmapaaralan |
| 114521 | Balogo Elementary School | Region V | SORSOGON | CITY OF SORSOGON (Capital) | BALOGO | osmapaaralan |
| 114553 | Balogo Elementary School | Region V | SORSOGON | CITY OF SORSOGON (Capital) | BALOGO | monitoring_validated |
| 106042 | Bancal Pugad Integrated School | Region III | PAMPANGA | LUBAO | BANCAL PUGAD | osmapaaralan |
| 306947 | Bancal Pugad Integrated School | Region III | PAMPANGA | LUBAO | BANCAL PUGAD | osmapaaralan |
| 107004 | Batiawan Integrated School Annex | Region III | ZAMBALES | SUBIC | BATIAWAN | osmapaaralan |
| 307110 | Batiawan Integrated School Annex | Region III | ZAMBALES | SUBIC | BATIAWAN | osmapaaralan |
| 114525 | Buenavista Elementary School | Region V | SORSOGON | CITY OF SORSOGON (Capital) | BUENAVISTA | osmapaaralan |
| 114568 | Buenavista Elementary School | Region V | SORSOGON | CITY OF SORSOGON (Capital) | BUENAVISTA | osmapaaralan |
| 133593 | Cadayonan PS | BARMM | LANAO DEL SUR | BAYANG | CADAYONAN | nsbi_2324 |
| 133679 | Cadayonan PS | BARMM | LANAO DEL SUR | BAYANG | CADAYONAN | nsbi_2324 |
| 173557 | Camarines Sur Sports Academy | Region V | CAMARINES SUR | PILI (Capital) | SAN JOSE | monitoring_validated |
| 309763 | Camarines Sur Sports Academy | Region V | CAMARINES SUR | PILI (Capital) | SAN JOSE | osmapaaralan |
| 305431 | Captain Albert Aguilar National HS | NCR | NCR FOURTH DISTRICT | CITY OF LAS PINAS | B.F. INTL VILLAGE | osmapaaralan |
| 320302 | Captain Albert Aguilar National HS | NCR | NCR FOURTH DISTRICT | CITY OF LAS PINAS | B.F. INTL VILLAGE | osmapaaralan |
| 128602 | Cogon Elementary School | Region XI | DAVAO DEL NORTE | IGC OF SAMAL | COGON | osmapaaralan |
| 128686 | Cogon Elementary School | Region XI | DAVAO DEL NORTE | IGC OF SAMAL | COGON | osmapaaralan |
| 137011 | Dibabawon I Elementary School | Region XI | DAVAO DEL NORTE | KAPALONG | GUPITAN | osmapaaralan |
| 204505 | Dibabawon I Elementary School | Region XI | DAVAO DEL NORTE | KAPALONG | GUPITAN | monitoring_validated |
| 159524 | Don Antonio Lee Chi Uan IS | Region III | PAMPANGA | BACOLOR | CALIBUTBUT | monitoring_validated |
| 306925 | Don Antonio Lee Chi Uan IS | Region III | PAMPANGA | BACOLOR | CALIBUTBUT | monitoring_validated |
| 107859 | Halang Banaybanay Integrated School | Region IV-A | CAVITE | AMADEO | BANAYBANAY | osmapaaralan |
| 301195 | Halang Banaybanay Integrated School | Region IV-A | CAVITE | AMADEO | BANAYBANAY | osmapaaralan |
| 401100 | Holy Child Academy | *(blank)* | *(blank)* | *(blank)* | *(blank)* | osmapaaralan |
| 407501 | Holy Child Academy | *(blank)* | *(blank)* | *(blank)* | *(blank)* | osmapaaralan |
| 160513 | Josephine F. Khonghun SPED Center | Region III | ZAMBALES | SUBIC | WAWANDUE (POB.) | monitoring_validated |
| 307111 | Josephine F. Khonghun SPED Center | Region III | ZAMBALES | SUBIC | WAWANDUE (POB.) | osmapaaralan |
| 106317 | Lourdes Elementary School | Region III | TARLAC | BAMBAN | LOURDES | osmapaaralan |
| 106318 | Lourdes Elementary School | Region III | TARLAC | BAMBAN | LOURDES | osmapaaralan |
| 120014 | Mandaue City School for the Arts | Region VII | CEBU | MANDAUE CITY | CASILI | osmapaaralan |
| 312806 | Mandaue City School for the Arts | Region VII | CEBU | MANDAUE CITY | CASILI | monitoring_validated |
| 1403032 | Morning Dew Montessori School | *(blank)* | Rizal | Cainta | *(blank)* | osmapaaralan |
| 403032 | Morning Dew Montessori School | *(blank)* | Rizal | Cainta | *(blank)* | osmapaaralan |
| 158528 | Northville V Elementary School | Region III | BULACAN | BOCAUE | BATIA | monitoring_validated |
| 306729 | Northville V Elementary School | Region III | BULACAN | BOCAUE | BATIA | osmapaaralan |
| 108047 | Pulo ni Sara Integrated School | Region IV-A | CAVITE | MARAGONDON | PANTIHAN IV | osmapaaralan |
| 301211 | Pulo ni Sara Integrated School | Region IV-A | CAVITE | MARAGONDON | PANTIHAN IV | osmapaaralan |
| 114529 | Salvacion Elementary School | Region V | SORSOGON | CITY OF SORSOGON | SALVACION | osmapaaralan |
| 114580 | Salvacion Elementary School | Region V | SORSOGON | CITY OF SORSOGON | SALVACION | monitoring_validated |
| 108835 | San Francisco B Elem. School | Region IV-A | QUEZON | LOPEZ | SAN FRANCISCO B | osmapaaralan |
| 108852 | San Francisco B Elem. School | Region IV-A | QUEZON | LOPEZ | SAN FRANCISCO B | osmapaaralan |
| 112694 | San Pablo Integrated School | Region V | CAMARINES SUR | LIBMANAN | SAN PABLO | osmapaaralan |
| 309770 | San Pablo Integrated School | Region V | CAMARINES SUR | LIBMANAN | SAN PABLO | osmapaaralan |
| 106957 | Santa Fe Elementary School | Region III | ZAMBALES | SAN MARCELINO | SANTA FE | osmapaaralan |
| 106958 | Santa Fe Elementary School | Region III | ZAMBALES | SAN MARCELINO | SANTA FE | osmapaaralan |

---

### CHECK 2b: Same Name, Same Municipality, Different Barangay — 25 pairs, 49 rows

> **High suspicion.** Two schools share the same name and municipality but are in different barangays. This could be legitimate (a school with a main campus in one barangay and an annex in another) or a data error (the same school was assigned to different barangays by different sources).

#### Representative examples

**Likely data error (national high school with two barangay assignments):**

| school_id | school_name | municipality | barangay |
|-----------|-------------|-------------|----------|
| 320805 | Currimao National High School | CURRIMAO | PIAS NORTE |
| 300013 | Currimao National High School | CURRIMAO | POBLACION II |

> A national high school typically has one campus. Having it listed in two different barangays suggests one source geocoded it to the wrong barangay. The coordinates would tell us which is correct.

**Likely legitimate (annex in different barangay):**

| school_id | school_name | municipality | barangay |
|-----------|-------------|-------------|----------|
| 325504 | Bukidnon NHS - Dalwangan Annex | CITY MALAYBALAY | DALWANGAN |
| 325505 | Bukidnon NHS - Dalwangan Annex | CITY MALAYBALAY | APO MACOTE |

> The name itself says "Annex." This could be a single annex that straddles two barangays, or two distinct annex campuses.

**Multiple entries in a large city:**

| school_id | school_name | municipality | barangay |
|-----------|-------------|-------------|----------|
| 126098 | Baluno Elementary School | ZAMBOANGA CITY | BALUNO |
| 126151 | Baluno Elementary School | ZAMBOANGA CITY | BUNGUIAO |
| 126196 | Baluno Elementary School | ZAMBOANGA CITY | SALAAN |

> Three entries for the same school name in three different barangays. Zamboanga City is very large (over 700 km²). It's plausible that three barangays each have their own "Baluno ES" — but "Baluno" is specific enough that this warrants investigation.

#### Notable cases

| school_ids | school_name | municipality | barangays |
|-----------|-------------|-------------|-----------|
| 301280 / 301281 | Abuyon National High School | SAN NARCISO | ABUYON / GUINHALINAN |
| 126098 / 126151 / 126196 | Baluno Elementary School | ZAMBOANGA CITY | BALUNO / BUNGUIAO / SALAAN |
| 325504 / 325505 | Bukidnon NHS - Dalwangan Annex | CITY MALAYBALAY | DALWANGAN / APO MACOTE |
| 320805 / 300013 | Currimao National High School | CURRIMAO | PIAS NORTE / POBLACION II |
| 304365 / 316214 | Erico T. Nograles NHS | DAVAO CITY | BGY. 37-D / BUNAWAN |
| 129550 / 129615 | Magsaysay Elementary School | DAVAO CITY | DALIAO / MAGSAYSAY |
| 304476 / 304478 | Matalam National High School | MATALAM | LINAO / POBLACION |
| 300996 / 300997 | Tarlac National High School | CITY OF TARLAC | SAN ROQUE / SAN MIGUEL |

---

### CHECK 2c: Same Name, Same Province, Different Municipality — 4,431 rows

> **Moderate suspicion (expected).** This is normal for the Philippines where barangay names — and thus school names — repeat across municipalities. Schools are typically named after their barangay, and barangay names like San Isidro, San Jose, and San Vicente are extremely common.

**Top 10 most repeated names within a single province:**

| School Name | Occurrences |
|-------------|-------------|
| San Isidro Elementary School | 186 |
| San Jose Elementary School | 147 |
| San Vicente Elementary School | 114 |
| San Roque Elementary School | 110 |
| Santo Nino Elementary School | 86 |
| San Antonio Elementary School | 84 |
| Santa Cruz Elementary School | 81 |
| San Juan Elementary School | 79 |
| Salvacion Elementary School | 62 |
| San Miguel Elementary School | 62 |

**No action needed.** These are distinct schools in distinct municipalities that share names due to Philippine naming conventions.

---

### CHECK 2d: Same Name, Same Region, Different Province — 3,057 rows

> **Low suspicion (expected).** Same pattern as 2c but across provinces within a region. **1,025 unique names** involved. **No action needed.**

---

### CHECK 3: Near-Identical Name Matching — 6 pairs, 12 rows

> **Highest suspicion.** These are schools in the same municipality whose names are clearly the same school but written differently. The pipeline preserves whatever name each source provides — it doesn't standardize school names — so abbreviation and formatting differences survive into the output.

#### All 6 pairs with explanations

**Abbreviation: "ES" vs "Elementary School"**

| school_id | school_name | municipality | match_reason |
|-----------|-------------|-------------|-------------|
| 136616 | Bagong Silang Elementary School | KALOOKAN CITY | Full name |
| 136639 | Bagong Silang ES | KALOOKAN CITY | Abbreviated |

> "ES" is the standard DepEd abbreviation for "Elementary School." One source used the full name, the other used the abbreviation. Same school.

**Abbreviation: "ES" vs "Elementary School" (second instance)**

| school_id | school_name | municipality | match_reason |
|-----------|-------------|-------------|-------------|
| 124285 | Sipit Elementary School | GODOD | Full name |
| 124291 | Sipit ES | GODOD | Abbreviated |

**Abbreviation: "Santa" vs "Sta."**

| school_id | school_name | municipality | match_reason |
|-----------|-------------|-------------|-------------|
| 116743 | Santa Ana National High School | SAN JOAQUIN | Spelled out |
| 305704 | Sta. Ana National High School | SAN JOAQUIN | Abbreviated |

> "Santa" and "Sta." are interchangeable in Philippine usage. Same school — one source spelled it out, the other abbreviated.

**Case difference only**

| school_id | school_name | municipality | match_reason |
|-----------|-------------|-------------|-------------|
| 126970 | Matampay Primary School | BALOI | Title case |
| 137025 | MATAMPAY PRIMARY SCHOOL | BALOI | Upper case |

> Identical name, different casing. Same school from two sources with different formatting conventions.

**Extra spacing**

| school_id | school_name | municipality | match_reason |
|-----------|-------------|-------------|-------------|
| 121681 | Sta. Paz Integrated School | MATALOM | Normal spacing |
| 313337 | Sta. Paz&nbsp;&nbsp;Integrated&nbsp;&nbsp;School | MATALOM | Double spaces |

> Same school. The double spaces are a data entry artifact from one source.

**Punctuation variation**

| school_id | school_name | municipality | match_reason |
|-----------|-------------|-------------|-------------|
| 136933 | Ramon M. Durano Sr. Foundation - Science and Technology HS | DANAO CITY | Hyphen separator |
| 322003 | Ramon M. Durano, Sr. Foundation Science and Technology HS | DANAO CITY | Comma, no hyphen |

> Differences: a comma after "Durano" vs a period, and a hyphen before "Science" in one version. Same school.

---

### CHECK 4: Null/Blank School Names — 3 rows

> These are schools that exist in the output with no name at all. All three have `15XXXXX` IDs — the `1X` pattern from Check 5.

| school_id | region | province | municipality | barangay | coord_source | has_coords |
|-----------|--------|----------|-------------|----------|-------------|------------|
| 1501028 | BARMM | LANAO DEL SUR | MALABANG | TUBOC | *(null)* | No |
| 1502670 | *(null)* | Laguna | Calamba | *(null)* | osmapaaralan | Yes |
| 1502829 | Region III | PAMPANGA | BACOLOR | SAN ANTONIO | *(null)* | No |

**Context:**
- **1502670** is the `1X` counterpart of `502670` (Punta Elementary School). The base record has a name; the `1X` version does not. This is a clear merge candidate.
- **1501028** and **1502829** have no coordinates and no coordinate source — they are phantom records created by the crosswalk from the School ID Mapping tab. They have location data but nothing else.

---

### CHECK 5: XXXXXX vs 1XXXXXX Pattern — 236 pairs

> **Systematic duplication.** DepEd's School ID Mapping has two ID columns: `BEIS School ID` (6 digits, e.g., `500570`) and `school_id_2024` (7 digits with leading `1`, e.g., `1500570`). Our crosswalk treats both as canonical IDs, creating 236 pairs where the same physical school appears twice under two different ID formats.

#### Classification

| Category | Count | Description |
|----------|-------|-------------|
| Same name | 81 | Both IDs have the exact same `school_name` |
| Different name | 155 | The two IDs have different `school_name` values |
| Same location fields | 1 | Only Morning Dew Montessori (403032 / 1403032) |

#### Representative examples

**Same school, same name (81 pairs) — clearly duplicates:**

| X ID | 1X ID | school_name | region |
|------|-------|-------------|--------|
| 500334 | 1500334 | Jose Fabella Memorial School | NCR |
| 500061 | 1500061 | Don Alipio Fernandez, Sr. IS | Region I |
| 500070 | 1500070 | San Jose Integrated School | Region II |
| 500124 | 1500124 | Aranguren Integrated School | Region III |
| 500167 | 1500167 | Cristo Rey Integrated School | Region V |

> Same name, same school. The `1X` version consistently has title-case province names (e.g., "Camarines Sur") vs UPPER CASE in the base version, and often has null barangay fields — telltale signs of a different data import pathway.

**Same school, abbreviation difference (~30 pairs) — likely duplicates:**

| X ID | X name | 1X ID | 1X name |
|------|--------|-------|---------|
| 500171 | Lezo IS | 1500171 | Lezo Integrated School |

> "IS" is the abbreviation of "Integrated School." Same school, but the exact-name check didn't catch it because the strings differ.

**Genuinely different schools (~55 pairs) — retain both:**

| X ID | X name | X region | 1X ID | 1X name | 1X region |
|------|--------|----------|-------|---------|-----------|
| 500002 | Rosario Integrated School | Region I | 1500002 | Angeles National High School | NCR |

> Completely different schools in different regions. They share the X/1X pattern coincidentally.

**Elementary + High School at same campus (~70 pairs) — retain both:**

| X ID | X name | 1X ID | 1X name |
|------|--------|-------|---------|
| 500223 | Babag Elementary School | 1500223 | Babag National High School |

> Distinct school levels (elementary vs high school) at the same campus. In DepEd's system, these are separate entities with separate enrollments and budgets. Both should be retained.

---

## Recommended Actions

### Check 2a: Same Name, Same Barangay (25 pairs)

| Pair | school_ids | Action | Justification |
|------|-----------|--------|---------------|
| Ali-is IS | 120120 / 501131 | **Merge** | Same school, different sources (OSM vs monitoring) |
| Amadeo IS | 107857 / 301166 | **Merge** | Same location, old ES ID + new ID |
| Balanti ES | 109393 / 109394 | **Merge** | Sequential IDs, same school |
| Balogo ES | 114521 / 114553 | **Merge** | Same school, OSM vs monitoring |
| Bancal Pugad IS | 106042 / 306947 | **Merge** | Old ID + new ID for integrated school |
| Batiawan IS Annex | 107004 / 307110 | **Merge** | Old ID + new ID |
| Buenavista ES | 114525 / 114568 | **Merge** | Same school, different source records |
| Cadayonan PS | 133593 / 133679 | **Investigate** | Both from NSBI — possible data entry error vs distinct campuses |
| Cam Sur Sports Academy | 173557 / 309763 | **Merge** | Same school, monitoring vs OSM |
| Capt. Albert Aguilar NHS | 305431 / 320302 | **Merge** | Both OSM, likely duplicate mapping |
| Cogon ES | 128602 / 128686 | **Investigate** | Both OSM, IDs 84 apart — verify coordinates |
| Dibabawon I ES | 137011 / 204505 | **Merge** | Same school, OSM vs monitoring |
| Don Antonio Lee Chi Uan IS | 159524 / 306925 | **Merge** | Both monitoring, old + new ID |
| Halang Banaybanay IS | 107859 / 301195 | **Merge** | Old ID + new ID |
| Holy Child Academy | 401100 / 407501 | **Investigate** | Both blank location — may be private schools |
| Josephine F. Khonghun SPED | 160513 / 307111 | **Merge** | Monitoring vs OSM |
| Lourdes ES | 106317 / 106318 | **Investigate** | Sequential IDs, both OSM — verify coordinates |
| Mandaue City School for the Arts | 120014 / 312806 | **Merge** | OSM vs monitoring |
| Morning Dew Montessori | 1403032 / 403032 | **Merge** | X/1X pattern, same school |
| Northville V ES | 158528 / 306729 | **Merge** | Monitoring vs OSM |
| Pulo ni Sara IS | 108047 / 301211 | **Merge** | Old ID + new ID |
| Salvacion ES | 114529 / 114580 | **Merge** | OSM vs monitoring |
| San Francisco B Elem. | 108835 / 108852 | **Investigate** | Both OSM, IDs 17 apart — verify coordinates |
| San Pablo IS | 112694 / 309770 | **Merge** | Old ID + new ID |
| Santa Fe ES | 106957 / 106958 | **Investigate** | Sequential IDs, both OSM — verify coordinates |

### Check 3: Near-Identical Names (6 pairs)

| Pair | school_ids | Action | Justification |
|------|-----------|--------|---------------|
| Bagong Silang ES variants | 136616 / 136639 | **Merge** | Abbreviation difference only |
| Matampay PS | 126970 / 137025 | **Merge** | Case difference only |
| Ramon M. Durano Sr. Foundation | 136933 / 322003 | **Merge** | Punctuation difference only |
| Santa Ana / Sta. Ana NHS | 116743 / 305704 | **Merge** | Abbreviation (Santa vs Sta.) |
| Sta. Paz IS | 121681 / 313337 | **Merge** | Extra spacing only |
| Sipit ES variants | 124285 / 124291 | **Merge** | Abbreviation difference only |

### Check 4: Null Names (3 records)

| school_id | Action | Justification |
|-----------|--------|---------------|
| 1501028 | **Investigate** | No name, no coordinates, 1X pattern — may be invalid record |
| 1502670 | **Correct ID** | 1X duplicate of 502670 (Punta ES) — merge with base record |
| 1502829 | **Investigate** | No name, no coordinates, 1X pattern — may be invalid record |

### Check 5: X/1X Pairs (236 pairs)

| Category | Count | Action | Justification |
|----------|-------|--------|---------------|
| Same name, same location | 1 | **Merge** | Morning Dew Montessori (also in Check 2a) |
| Same name, different metadata | 80 | **Investigate** | Likely same school from different sources; 1X version has title-case names and null barangay |
| Different name, ES/NHS pair | ~70 | **Retain Both** | Intentional: elementary and high school at same campus |
| Different name, abbreviation variant | ~30 | **Investigate** | May be abbreviation duplicates (e.g., "Lezo IS" vs "Lezo Integrated School") |
| Different name, completely different | ~55 | **Retain Both** | Different schools that coincidentally share the X/1X pattern |

### Check 2b: Same Municipality, Different Barangay (25 pairs)

**Investigate all.** May be legitimate branch campuses or barangay misassignment. Spot-check coordinates to confirm they are truly at different physical locations.

### Checks 2c/2d: Same Province/Region

**Retain all.** Expected Philippine naming convention. No action needed.

---

## Appendix: Ambiguous Cases

### A1: Holy Child Academy (401100 / 407501)

Both records have completely blank geographic data (no region, province, municipality, or barangay). Both are from OSMapaaralan. The school IDs fall in the private school range (`400xxx` / `407xxx`), suggesting these may be private schools that survived the private-school exclusion filter because their IDs weren't in the TOSF or enrollment files.

**Recommendation:** Verify whether these are private schools and remove from the public dataset if confirmed.

### A2: Sequential OSM IDs in the same barangay

Three pairs from Check 2a have sequential or near-sequential IDs (106317/106318, 106957/106958, 108835/108852), all from OSMapaaralan. These could represent:
- A data entry error in OSM where the same school was mapped twice with slightly different ref values
- Distinct school levels (e.g., elementary and preschool) that share a name and campus but have different IDs

**Recommendation:** Check if the coordinates are within 50 meters of each other. If yes, merge. If no, retain both and investigate the OSM source data.

### A3: The 1X pattern at scale (236 pairs)

The `school_id_2024` column in DepEd's School ID Mapping uses a `1XXXXXX` format for some schools, while the `BEIS School ID` column uses `XXXXXX`. Both are treated as canonical IDs by the crosswalk, creating systematic duplication. This is a **source data architecture issue** — the School ID Mapping tab has two different ID columns that both get treated as separate canonical entries.

Resolving this at the pipeline level would require choosing one format as authoritative (BEIS vs school_id_2024), which is a policy decision beyond the scope of this audit.

### A4: Cadayonan PS (133593 / 133679)

Both IDs come from NSBI (not from different sources), both in the same barangay in Bayang, Lanao del Sur. This is unusual — most Check 2a pairs come from different data sources. This may be a genuine data entry error in the NSBI system where the same school was assigned two IDs.

**Recommendation:** Cross-reference with the enrollment file to determine which ID is actively used.
