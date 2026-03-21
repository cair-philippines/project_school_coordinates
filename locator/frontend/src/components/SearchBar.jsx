import { useState, useEffect, useRef } from "react";
import { Search, X, MapPin, School } from "lucide-react";

export default function SearchBar({ onSearch, onSelect, results, loading }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);
  const debounceRef = useRef(null);
  // Flag to suppress the search effect when query changes due to selection
  const isSelectingRef = useRef(false);

  // Debounced search — only fires for user typing, not programmatic selection
  useEffect(() => {
    if (isSelectingRef.current) {
      isSelectingRef.current = false;
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.length >= 2) {
      debounceRef.current = setTimeout(() => {
        onSearch(query);
        setOpen(true);
      }, 250);
    } else if (query.length === 0) {
      onSearch("");
      setOpen(false);
    } else {
      setOpen(false);
    }
    return () => clearTimeout(debounceRef.current);
  }, [query, onSearch]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const handleSelect = (school) => {
    isSelectingRef.current = true;
    setQuery(school.school_name || school.school_id);
    setOpen(false);
    onSelect(school);
  };

  const handleClear = () => {
    isSelectingRef.current = false;
    setQuery("");
    setOpen(false);
    onSelect(null);
    inputRef.current?.focus();
  };

  return (
    <div ref={wrapperRef} className="relative w-full">
      <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 shadow-sm transition-shadow focus-within:shadow-md focus-within:border-[var(--ring)]">
        <Search className="h-5 w-5 shrink-0 text-[var(--muted-foreground)]" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by school name or ID..."
          className="flex-1 bg-transparent text-base outline-none placeholder:text-[var(--muted-foreground)]"
        />
        {query && (
          <button
            onClick={handleClear}
            className="shrink-0 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-2 max-h-80 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg z-50">
          {loading && (
            <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
              Searching...
            </div>
          )}
          {!loading && results.length === 0 && query.length >= 2 && (
            <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
              No schools found.
            </div>
          )}
          {results.slice(0, 20).map((school) => (
            <button
              key={school.school_id}
              onClick={() => handleSelect(school)}
              className="w-full text-left flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-[var(--accent)] transition-colors border-b border-[var(--border)] last:border-b-0"
            >
              <div className="mt-0.5 shrink-0">
                <School
                  className={`h-4 w-4 ${
                    school.sector === "public"
                      ? "text-blue-600"
                      : "text-pink-600"
                  }`}
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">
                  {school.school_name || "Unnamed"}
                </div>
                <div className="text-xs text-[var(--muted-foreground)] mt-0.5 flex items-center gap-1">
                  <MapPin className="h-3 w-3 shrink-0" />
                  <span className="truncate">
                    {[school.municipality, school.province]
                      .filter(Boolean)
                      .join(", ") || "No location data"}
                  </span>
                </div>
                <div className="text-xs text-[var(--muted-foreground)] mt-0.5">
                  {school.school_id} &middot; {school.sector}
                </div>
              </div>
            </button>
          ))}
          {results.length > 20 && (
            <div className="px-4 py-2 text-xs text-[var(--muted-foreground)] text-center border-t border-[var(--border)]">
              Showing 20 of {results.length.toLocaleString()} results
            </div>
          )}
        </div>
      )}
    </div>
  );
}
