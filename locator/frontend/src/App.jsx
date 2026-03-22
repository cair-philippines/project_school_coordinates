import { useState, useEffect, useCallback, useRef } from "react";
import { MapPin, Map, Table2 } from "lucide-react";
import SearchBar from "./components/SearchBar";
import SchoolMap from "./components/SchoolMap";
import SchoolTable from "./components/SchoolTable";
import StatsBar from "./components/StatsBar";
import ResultsList from "./components/ResultsList";
import FilterPanel from "./components/FilterPanel";
import SummaryCard from "./components/SummaryCard";
import SchoolDetail from "./components/SchoolDetail";
import { useSchools } from "./hooks/useSchools";
import "./index.css";

/**
 * Interaction modes:
 *   "idle"   — no search or filter active, map shows Philippines
 *   "search" — user typed a search query
 *   "filter" — user selected location filters
 */

function App() {
  const {
    results,
    total,
    loading,
    stats,
    filters,
    searchSchools,
    fetchFilters,
    fetchStats,
  } = useSchools();

  const [mode, setMode] = useState("idle");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilters, setActiveFilters] = useState({});
  const [selectedSchool, setSelectedSchool] = useState(null); // highlighted on map
  const [detailSchool, setDetailSchool] = useState(null); // detail panel open
  const [flyToTrigger, setFlyToTrigger] = useState(0); // incremented to force map fly-to
  const [searchClearSignal, setSearchClearSignal] = useState(0);
  const [viewMode, setViewMode] = useState("map"); // "map" or "table"

  // Tracks whether filter change was programmatic (from clearing) vs user-initiated
  const filterChangeIsReset = useRef(false);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // Single effect that drives the API call based on current mode
  useEffect(() => {
    if (mode === "search" && searchQuery) {
      searchSchools({
        q: searchQuery,
        limit: 200,
      });
    } else if (mode === "filter") {
      const hasLocation = activeFilters.region || activeFilters.province ||
        activeFilters.municipality || activeFilters.barangay;
      if (hasLocation) {
        searchSchools({
          ...activeFilters,
        });
      } else {
        // Filters were cleared — go idle
        searchSchools({ _clear: true });
        setMode("idle");
      }
    } else if (mode === "idle") {
      searchSchools({ _clear: true });
    }
  }, [mode, searchQuery, activeFilters, searchSchools]);

  // --- Search handlers ---
  const handleSearch = useCallback((query) => {
    if (query && query.length >= 2) {
      setSearchQuery(query);
      setMode("search");
      setSelectedSchool(null);
      // Clear filters without triggering a filter-mode search
      filterChangeIsReset.current = true;
      setActiveFilters({});
    } else {
      setSearchQuery("");
      // Only go idle if we're in search mode (don't disrupt filter mode)
      setMode((prev) => (prev === "search" ? "idle" : prev));
      setSelectedSchool(null);
    }
  }, []);

  const handleSearchSelect = useCallback((school) => {
    if (school) {
      setSelectedSchool(school);
      setDetailSchool(null); // don't auto-open detail panel
      setFlyToTrigger((c) => c + 1);
    } else {
      // Search cleared
      setSearchQuery("");
      setSelectedSchool(null);
      setDetailSchool(null);
      setMode("idle");
    }
  }, []);

  // --- Filter handlers ---
  const handleFilterChange = useCallback((newFilters) => {
    // If this change came from programmatic reset, don't switch to filter mode
    if (filterChangeIsReset.current) {
      filterChangeIsReset.current = false;
      return;
    }
    const hasLocation = newFilters.region || newFilters.province ||
      newFilters.municipality || newFilters.barangay;
    if (hasLocation) {
      // If switching from search mode, clear results first so the map
      // sees an empty→populated transition and zooms to new bounds
      if (mode === "search") {
        searchSchools({ _clear: true });
      }
      setSearchQuery("");
      setSearchClearSignal((c) => c + 1);
      setSelectedSchool(null);
      setActiveFilters(newFilters);
      setMode("filter");
    } else {
      setActiveFilters(newFilters);
      setMode("idle");
      setSelectedSchool(null);
    }
  }, [mode, searchSchools]);

  // --- School selection from results list or table ---
  const handleSelectFromList = useCallback((school) => {
    setSelectedSchool(school);
    setDetailSchool(null); // don't auto-open detail panel
    setFlyToTrigger((c) => c + 1);
    if (viewMode === "table") {
      setViewMode("map");
    }
  }, [viewMode]);

  // --- Detail panel: opened by clicking the highlighted marker on the map ---
  const handleOpenDetail = useCallback((school) => {
    setDetailSchool(school);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setDetailSchool(null);
    // Don't clear selectedSchool or change mode — the map stays where it is
  }, []);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="shrink-0 border-b border-[var(--border)] bg-[var(--card)]">
        <div className="px-4 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <div className="h-8 w-8 rounded-lg bg-[var(--primary)] flex items-center justify-center">
              <MapPin className="h-4.5 w-4.5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold leading-tight">School Locator</h1>
              <p className="text-[11px] text-[var(--muted-foreground)] leading-tight">
                Philippine Public &amp; Private Schools
              </p>
            </div>
          </div>
          <div className="flex-1 max-w-xl">
            <SearchBar
              onSearch={handleSearch}
              onSelect={handleSearchSelect}
              results={mode === "search" ? results : []}
              loading={mode === "search" && loading}
              externalClear={searchClearSignal}
            />
          </div>
        </div>
        <div className="px-4 pb-2">
          <StatsBar stats={stats} />
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 flex min-h-0 relative">
        {/* Left sidebar */}
        <aside className="w-80 shrink-0 border-r border-[var(--border)] bg-[var(--card)] flex flex-col min-h-0">
          <FilterPanel
            onFilterChange={handleFilterChange}
            fetchFilters={fetchFilters}
            filters={filters}
          />
          {mode === "filter" && <SummaryCard activeFilters={activeFilters} />}
          <div className="flex-1 min-h-0 overflow-hidden">
            <ResultsList
              results={mode !== "idle" ? results : []}
              total={mode !== "idle" ? total : 0}
              loading={loading}
              onSelect={handleSelectFromList}
              selectedId={selectedSchool?.school_id}
            />
          </div>
        </aside>

        {/* Main view area */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* View toggle */}
          <div className="shrink-0 flex items-center gap-1 px-2 pt-2">
            <button
              onClick={() => setViewMode("map")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                viewMode === "map"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--accent)]"
              }`}
            >
              <Map className="h-3.5 w-3.5" />
              Map
            </button>
            <button
              onClick={() => setViewMode("table")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                viewMode === "table"
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                  : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--accent)]"
              }`}
            >
              <Table2 className="h-3.5 w-3.5" />
              Table
            </button>
          </div>

          {/* Map + Table + Detail overlay share the same space */}
          <div className="flex-1 p-2 min-h-0 relative">
            {/* Map — always mounted, visually hidden when table is active */}
            <div className={`absolute inset-2 ${viewMode === "map" ? "z-10" : "z-0 opacity-0 pointer-events-none"}`}>
              <SchoolMap
                schools={mode !== "idle" ? results : []}
                selectedSchool={selectedSchool}
                onOpenDetail={handleOpenDetail}
                mode={mode}
                flyToTrigger={flyToTrigger}
              />
            </div>

            {/* Table — rendered on top when active */}
            {viewMode === "table" && (
              <div className="absolute inset-2 z-10">
                <SchoolTable
                  schools={mode !== "idle" ? results : []}
                  onSelect={handleSelectFromList}
                  selectedId={selectedSchool?.school_id}
                />
              </div>
            )}

            {/* School detail — overlays on the map, opened by clicking highlighted marker */}
            {detailSchool && (
              <div className="absolute top-4 right-4 bottom-4 z-20">
                <SchoolDetail school={detailSchool} onClose={handleCloseDetail} />
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
