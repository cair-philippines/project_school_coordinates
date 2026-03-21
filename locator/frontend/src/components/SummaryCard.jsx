import { useEffect, useState } from "react";
import {
  Building2,
  MapPin,
  Users,
  BarChart3,
  Eye,
  GraduationCap,
} from "lucide-react";

function Stat({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${color || "text-[var(--muted-foreground)]"}`} />
      <div>
        <div className="text-lg font-semibold leading-tight">{value}</div>
        <div className="text-[11px] text-[var(--muted-foreground)]">{label}</div>
        {sub && <div className="text-[11px] text-[var(--muted-foreground)]">{sub}</div>}
      </div>
    </div>
  );
}

function SourceBar({ sources }) {
  if (!sources || Object.keys(sources).length === 0) return null;
  const total = Object.values(sources).reduce((a, b) => a + b, 0);
  const colors = {
    monitoring_validated: "#10b981",
    osmapaaralan: "#3b82f6",
    nsbi_2324: "#8b5cf6",
    geolocation_deped: "#f59e0b",
    tosf_self_reported: "#ec4899",
    none: "#d1d5db",
  };
  const labels = {
    monitoring_validated: "Monitoring",
    osmapaaralan: "OSMapaaralan",
    nsbi_2324: "NSBI",
    geolocation_deped: "Geolocation",
    tosf_self_reported: "TOSF",
    none: "No coords",
  };

  return (
    <div className="space-y-1.5">
      <div className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide flex items-center gap-1">
        <Eye className="h-3 w-3" />
        Coordinate Sources
      </div>
      <div className="flex h-2 rounded-full overflow-hidden bg-gray-100">
        {Object.entries(sources)
          .sort(([, a], [, b]) => b - a)
          .map(([src, count]) => (
            <div
              key={src}
              style={{
                width: `${(count / total) * 100}%`,
                backgroundColor: colors[src] || "#94a3b8",
              }}
              title={`${labels[src] || src}: ${count.toLocaleString()}`}
            />
          ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {Object.entries(sources)
          .sort(([, a], [, b]) => b - a)
          .map(([src, count]) => (
            <div key={src} className="flex items-center gap-1 text-[10px] text-[var(--muted-foreground)]">
              <div
                className="h-2 w-2 rounded-full shrink-0"
                style={{ backgroundColor: colors[src] || "#94a3b8" }}
              />
              {labels[src] || src}: {count.toLocaleString()}
            </div>
          ))}
      </div>
    </div>
  );
}

export default function SummaryCard({ activeFilters }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const hasFilter = activeFilters && Object.values(activeFilters).some(Boolean);
    if (!hasFilter) {
      setSummary(null);
      return;
    }

    setLoading(true);
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(activeFilters)) {
      if (v) qs.set(k, v);
    }
    fetch(`/api/summary?${qs}`)
      .then((r) => r.json())
      .then((data) => setSummary(data))
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [activeFilters]);

  if (!summary) return null;
  if (loading) {
    return (
      <div className="p-3 border-b border-[var(--border)] text-xs text-[var(--muted-foreground)] animate-pulse">
        Loading summary...
      </div>
    );
  }

  const label = [
    activeFilters?.municipality,
    activeFilters?.province,
    activeFilters?.region,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="p-3 border-b border-[var(--border)] bg-gradient-to-b from-[var(--accent)] to-[var(--card)] space-y-3">
      <div className="text-xs font-medium text-[var(--muted-foreground)]">
        {label || "Summary"}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat icon={Building2} label="Total Schools" value={summary.total.toLocaleString()} color="text-[var(--primary)]" />
        <Stat
          icon={MapPin}
          label="With Coords"
          value={`${summary.coverage_pct}%`}
          sub={`${summary.with_coordinates.toLocaleString()} of ${summary.total.toLocaleString()}`}
          color="text-green-600"
        />
        <Stat
          icon={Building2}
          label="Public"
          value={summary.public.toLocaleString()}
          color="text-blue-600"
        />
        <Stat
          icon={Building2}
          label="Private"
          value={summary.private.toLocaleString()}
          color="text-pink-600"
        />
        <Stat
          icon={Users}
          label="Active Enrollment"
          value={summary.active_enrollment.toLocaleString()}
          color="text-emerald-600"
        />
        <Stat
          icon={Users}
          label="No Enrollment"
          value={summary.no_enrollment_reported.toLocaleString()}
          color="text-amber-600"
        />
      </div>

      {summary.gastpe && (summary.gastpe.esc > 0 || summary.gastpe.shsvp > 0) && (
        <div className="space-y-1">
          <div className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide flex items-center gap-1">
            <GraduationCap className="h-3 w-3" />
            GASTPE (Private)
          </div>
          <div className="flex gap-3 text-xs">
            <span>ESC: <b>{summary.gastpe.esc.toLocaleString()}</b></span>
            <span>SHS VP: <b>{summary.gastpe.shsvp.toLocaleString()}</b></span>
            <span>JDVP: <b>{summary.gastpe.jdvp.toLocaleString()}</b></span>
          </div>
        </div>
      )}

      <SourceBar sources={summary.coord_sources} />
    </div>
  );
}
