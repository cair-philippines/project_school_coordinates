import { useState, useCallback } from "react";

const API_BASE = "/api";

export function useSchools() {
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({
    regions: [],
    provinces: [],
    municipalities: [],
    barangays: [],
  });

  const searchSchools = useCallback(async (params = {}) => {
    // Handle clear signal
    if (params._clear) {
      setResults([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined && v !== "") qs.set(k, v);
      }
      const res = await fetch(`${API_BASE}/schools?${qs}`);
      const data = await res.json();
      setResults(data.results);
      setTotal(data.total);
    } catch (err) {
      console.error("Search failed:", err);
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchFilters = useCallback(async (params = {}) => {
    try {
      const qs = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== null && v !== undefined && v !== "") qs.set(k, v);
      }
      const res = await fetch(`${API_BASE}/filters?${qs}`);
      const data = await res.json();
      setFilters(data);
    } catch (err) {
      console.error("Filters failed:", err);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      const data = await res.json();
      setStats(data);
    } catch (err) {
      console.error("Stats failed:", err);
    }
  }, []);

  return {
    results,
    total,
    loading,
    stats,
    filters,
    searchSchools,
    fetchFilters,
    fetchStats,
  };
}
