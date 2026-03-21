import { useState, useEffect, useCallback, useRef } from "react";
import { MapPin } from "lucide-react";
import SearchBar from "./components/SearchBar";
import SchoolMap from "./components/SchoolMap";
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
  const [selectedSchool, setSelectedSchool] = useState(null);
  const [searchClearSignal, setSearchClearSignal] = useState(0);

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
        limit: 100,
        has_coords: true,
      });
    } else if (mode === "filter") {
      const hasLocation = activeFilters.region || activeFilters.province ||
        activeFilters.municipality || activeFilters.barangay;
      if (hasLocation) {
        searchSchools({
          ...activeFilters,
          has_coords: true,
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
      // Enter a "selected" sub-state within search mode
      // Don't change mode — keep "search" so the map controller
      // knows this is a fly-to-school, not a filter change
      setSelectedSchool(school);
    } else {
      // Search cleared
      setSearchQuery("");
      setSelectedSchool(null);
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
      if (mode === "search" || selectedSchool) {
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
  }, [mode, selectedSchool, searchSchools]);

  // --- School selection from results list ---
  const handleSelectFromList = useCallback((school) => {
    setSelectedSchool(school);
  }, []);

  const handleCloseDetail = useCallback(() => {
    setSelectedSchool(null);
    // In search mode, closing the detail panel resets to idle
    // (the user is done with that school)
    if (mode === "search") {
      setSearchQuery("");
      setSearchClearSignal((c) => c + 1);
      setMode("idle");
    }
  }, [mode]);

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

        {/* Map */}
        <div className="flex-1 p-2">
          <SchoolMap
            schools={mode !== "idle" ? results : []}
            selectedSchool={selectedSchool}
            mode={mode}
          />
        </div>

        {/* Right panel: school detail */}
        {selectedSchool && (
          <SchoolDetail school={selectedSchool} onClose={handleCloseDetail} />
        )}
      </main>
    </div>
  );
}

export default App;
