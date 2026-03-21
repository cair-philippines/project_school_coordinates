# Piring — School Locator

Interactive web application for searching and visualizing Philippine public and private school locations. Built on the unified coordinates datasets produced by this project's pipelines. "Piring" means blindfold in Filipino — the app reveals what's hidden in the data.

## Features

- **Search** — debounced type-ahead search by school name or ID with ranked results (exact ID > starts-with > contains); matching schools appear as passive markers on the map without auto-zooming; map flies to a school only when explicitly clicked
- **Cascading location filters** — Region → Province → Municipality → Barangay dropdowns with exact matching; map auto-zooms to the selected area
- **Summary cards** — when a location filter is active, shows total schools, public/private split, coordinate coverage %, enrollment status, GASTPE participation, and coordinate source breakdown bar
- **Interactive map** — Leaflet map with CARTO light basemap, PSGC-aware colored markers (green=public validated, blue=private validated, red pulsing=misplaced, gray=unvalidated), context-aware zoom, proportional sector sampling, IQR-based outlier-robust bounds
- **Table view** — togglable tabular view showing all matching schools including those without coordinates (invisible on the map). Sortable columns (click header to cycle asc/desc/clear): ID, name, sector, municipality, province, region, coord status, PSGC validation, enrollment status. Click a row to locate on the map (or zoom to locality if no coordinates).
- **Results sidebar** — scrollable list of all matching schools, showing school name, location, sector, and coordinate status badges
- **School detail panel** — slide-out panel with full school profile: location hierarchy, coordinate lineage (source, trust level, validator notes), GASTPE flags, enrollment status
- **Coordinate lineage inspector** — for each school, shows which source provided coordinates, trust level, available sources, and for monitoring-validated schools, which sub-source the validator chose
- **Stats bar** — live summary of total schools, public/private split, coordinate coverage, active enrollment

## Architecture

```
Browser
  └── React SPA (Vite + Tailwind)
        ├── SearchBar (debounced type-ahead)
        ├── FilterPanel (cascading dropdowns)
        ├── SummaryCard (admin-level stats)
        ├── SchoolMap (react-leaflet, PSGC-aware markers)
        ├── SchoolTable (tabular view with data quality indicators)
        ├── ResultsList
        ├── SchoolDetail (lineage inspector)
        └── StatsBar
              │
              ▼
        FastAPI backend (Python)
              └── loads parquet files at startup (~61K schools in memory)
```

Single container for deployment. The backend serves both the API and the built React static files.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, Tailwind CSS v4, lucide-react |
| Map | Leaflet + react-leaflet, CARTO Light basemap |
| Backend | FastAPI, pandas, pyarrow |
| Data | Parquet files from `data/modified/` |

## Running the App

### Production Mode (backend only)

Build the frontend once, then run the backend — it serves both the API and the static frontend files:

```bash
# From the devcontainer (where npm is available):
cd locator/frontend
npm install
npm run build

# From a Jupyter terminal (DS container):
cd /workspace/project_coordinates/locator/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000`. After any frontend code changes, re-run `npm run build` and refresh the browser.

### Development Mode (both servers)

For active frontend development with hot reload:

```bash
# Terminal 1 — DS container (Jupyter):
cd /workspace/project_coordinates/locator/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — devcontainer (where npm exists):
cd locator/frontend
npm run dev
```

Visit `http://localhost:5173`. The Vite proxy forwards `/api/*` to the backend.

### Port Requirements

The DS container's `docker-compose.yml` must expose ports 8000 and 5173:

```yaml
ports:
  - "8888:8888"
  - "8000:8000"
  - "5173:5173"
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/schools?q=&region=&...` | Search and filter schools; omit `limit` for all results |
| `GET /api/schools/{school_id}` | Single school detail |
| `GET /api/filters?region=&...` | Cascading filter options (exact match) |
| `GET /api/stats` | Global summary statistics |
| `GET /api/summary?region=&province=&...` | Admin-level summary (coord sources, GASTPE, enrollment) |

## Design Decisions

### Interaction Modes

The app operates in one of three modes at a time, preventing state conflicts:
- **Idle** — no search or filter active; map shows the Philippines, no markers
- **Search** — user typed a query; matching schools appear as passive markers on the map (no auto-zoom); map only flies to a school when the user explicitly clicks one in the dropdown
- **Filter** — user selected location dropdowns; results from exact location matching; map auto-zooms to fit all markers in the selected area

Starting a search clears filters. Selecting a filter clears the search. This eliminates the class of bugs where stale state from one mode bleeds into another.

### Map View Controller

The map's zoom behavior is managed by two independent effects:

1. **Fly-to effect** — triggered by a `flyToTrigger` counter that increments only when a user explicitly clicks a school (from search dropdown, results list, or table row). This is the highest priority zoom action. Calls `map.stop()` first to cancel any in-progress animation.
2. **Bounds effect** — triggered when the marker signature changes (filter results updated or cleared). Fits bounds to all markers in filter mode; does nothing in search mode.

These two effects don't interfere because they watch different signals. The fly-to trigger is a monotonic counter, not a reactive dependency chain — it can't be accidentally fired by unrelated state changes.

The map is always mounted (never unmounts when switching to table view). It's hidden with `opacity-0` and `pointer-events-none` behind the table, preserving the Leaflet instance and all its state. When clicking a school in the table, the map is revealed and the fly-to effect fires on the already-mounted map.

**Key invariant**: `handleFilterChange`'s React callback dependencies must NOT include `selectedSchool`. Including it causes the callback to regenerate when a school is selected, which triggers FilterPanel's effect, which re-invokes the filter handler, which clears and re-fetches results, which triggers a bounds fit that overrides the fly-to. This was the root cause of a persistent bug where table-to-map school selection would zoom to the filter area instead of the school.

### Location Filtering

All location filters use **case-insensitive exact matching** (not substring). This prevents:
- "Region V" matching Region VI, VII, VIII
- "CAR" matching CARAGA
- "Alfonso" matching "Alfonso Castañeda"

Location column values are normalized to consistent casing at data load time (title case for provinces/municipalities, preserved abbreviations for NCR, CAR, BARMM, etc.).

### Map Marker Capping

The map caps rendered markers at 3,000 for performance. When results exceed this cap, markers are **sampled proportionally by sector** — if a region has 64% public and 36% private schools, the marker sample preserves that ratio. This prevents one sector from visually disappearing due to load order.

Bounds calculation always uses the full (uncapped) result set to ensure correct zoom behavior.

### PSGC-Aware Marker Colors

Map markers reflect PSGC spatial validation status:
- **Green dot** — public school with `psgc_match` (coordinates confirmed within claimed barangay)
- **Blue dot** — private school with `psgc_match`
- **Green pulsing dot** — public school with `psgc_mismatch` (coordinates fall in a different barangay than claimed)
- **Blue pulsing dot** — private school with `psgc_mismatch`
- **Gray dot** — either sector with `psgc_no_validation` (has coordinates but couldn't be validated)

The pulsing animation uses the sector color (green/blue) so mismatched schools remain distinguishable by sector while the animation signals the coordinate discrepancy.

### Table View

A togglable tabular view that complements the map by showing **all** matching schools — including those without coordinates (invisible on the map). This surfaces data quality issues: schools with no coordinates, PSGC mismatches, and inactive enrollment.

Clicking a row switches to map view and:
- **If the school has coordinates** — flies to the school at zoom 16 and opens the detail panel
- **If the school has no coordinates** — zooms to the school's municipality/province/region (best-effort locality zoom using other schools in the same area) and opens the detail panel

### Outlier-Robust Bounds

When zooming to a location, the map computes bounds using an **IQR-based filter** that excludes spatial outliers (schools with stray coordinates far from the cluster). This prevents a single mislocated school from stretching the zoom level to show the entire country.

## Project Structure

```
locator/
├── backend/
│   ├── main.py               # FastAPI app + routes + SPA serving
│   ├── data_loader.py         # Parquet loading + location normalization
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main layout + mode management
│   │   ├── components/
│   │   │   ├── SearchBar.jsx   # Debounced search with selection handling
│   │   │   ├── FilterPanel.jsx # Cascading location dropdowns
│   │   │   ├── SummaryCard.jsx # Admin-level summary stats
│   │   │   ├── SchoolMap.jsx   # Leaflet map + PSGC-aware markers
│   │   │   ├── SchoolTable.jsx  # Tabular view with data quality indicators
│   │   │   ├── SchoolDetail.jsx # Slide-out detail + lineage inspector
│   │   │   ├── ResultsList.jsx  # Sidebar results
│   │   │   └── StatsBar.jsx    # Global summary stats
│   │   └── hooks/
│   │       └── useSchools.js   # API client
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Roadmap

- **Phase 3** — Docker + Google Cloud Run deployment
- **Phase 4** — Mobile responsive, loading states, polish
- **Future** — Nearby schools (radius search), choropleth dashboard, export to CSV/GeoJSON, bookmarkable URLs
