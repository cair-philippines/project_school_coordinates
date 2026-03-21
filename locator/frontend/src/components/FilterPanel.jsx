import { useState, useEffect } from "react";
import { Filter, ChevronDown, X } from "lucide-react";

function Dropdown({ label, value, options, onChange, disabled, placeholder }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide">
        {label}
      </label>
      <div className="relative">
        <select
          value={value || ""}
          onChange={(e) => onChange(e.target.value || null)}
          disabled={disabled}
          className="w-full appearance-none rounded-lg border border-[var(--border)] bg-[var(--card)] px-3 py-2 pr-8 text-sm outline-none transition-colors focus:border-[var(--ring)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <option value="">{placeholder || `All ${label}s`}</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--muted-foreground)] pointer-events-none" />
      </div>
    </div>
  );
}

export default function FilterPanel({ onFilterChange, fetchFilters, filters }) {
  const [region, setRegion] = useState(null);
  const [province, setProvince] = useState(null);
  const [municipality, setMunicipality] = useState(null);
  const [barangay, setBarangay] = useState(null);
  const [expanded, setExpanded] = useState(true);

  // Fetch filter options on mount and when cascading values change
  useEffect(() => {
    fetchFilters({ region, province, municipality });
  }, [region, province, municipality, fetchFilters]);

  // Notify parent of filter changes
  useEffect(() => {
    onFilterChange({ region, province, municipality, barangay });
  }, [region, province, municipality, barangay, onFilterChange]);

  const handleRegionChange = (val) => {
    setRegion(val);
    setProvince(null);
    setMunicipality(null);
    setBarangay(null);
  };

  const handleProvinceChange = (val) => {
    setProvince(val);
    setMunicipality(null);
    setBarangay(null);
  };

  const handleMunicipalityChange = (val) => {
    setMunicipality(val);
    setBarangay(null);
  };

  const hasFilters = region || province || municipality || barangay;

  const clearAll = () => {
    setRegion(null);
    setProvince(null);
    setMunicipality(null);
    setBarangay(null);
  };

  return (
    <div className="border-b border-[var(--border)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Filter className="h-3.5 w-3.5" />
          Location Filters
          {hasFilters && (
            <span className="inline-flex items-center justify-center h-4 w-4 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] text-[10px] font-bold">
              {[region, province, municipality, barangay].filter(Boolean).length}
            </span>
          )}
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          <Dropdown
            label="Region"
            value={region}
            options={filters.regions}
            onChange={handleRegionChange}
          />
          <Dropdown
            label="Province"
            value={province}
            options={filters.provinces}
            onChange={handleProvinceChange}
            disabled={!region}
          />
          <Dropdown
            label="Municipality"
            value={municipality}
            options={filters.municipalities}
            onChange={handleMunicipalityChange}
            disabled={!province}
          />
          <Dropdown
            label="Barangay"
            value={barangay}
            options={filters.barangays}
            onChange={setBarangay}
            disabled={!municipality}
          />

          {hasFilters && (
            <button
              onClick={clearAll}
              className="w-full flex items-center justify-center gap-1 text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] py-1.5 transition-colors"
            >
              <X className="h-3 w-3" />
              Clear all filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
