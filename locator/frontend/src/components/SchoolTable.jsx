import { MapPin, AlertCircle } from "lucide-react";

function StatusDot({ school }) {
  const hasCoords = school.latitude != null;
  const validation = school.psgc_validation;

  if (!hasCoords) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700">
        <AlertCircle className="h-3 w-3" />
        no coords
      </span>
    );
  }

  if (validation === "psgc_match") {
    const color = school.sector === "public" ? "bg-green-500" : "bg-blue-500";
    return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} title="Validated" />;
  }

  if (validation === "psgc_mismatch") {
    const dotColor = school.sector === "public" ? "bg-green-500" : "bg-blue-500";
    const pingColor = school.sector === "public" ? "bg-green-400" : "bg-blue-400";
    return (
      <span className="relative inline-block h-2.5 w-2.5">
        <span className={`absolute inset-0 rounded-full ${dotColor}`} />
        <span className={`absolute inset-0 rounded-full ${pingColor} animate-ping opacity-50`} />
      </span>
    );
  }

  // psgc_no_validation
  return <span className="inline-block h-2.5 w-2.5 rounded-full bg-gray-400" title="Unvalidated" />;
}

function ValidationBadge({ validation }) {
  if (!validation) return <span className="text-gray-400">—</span>;
  const styles = {
    psgc_match: "bg-green-50 text-green-700",
    psgc_mismatch: "bg-red-50 text-red-700",
    psgc_no_validation: "bg-gray-100 text-gray-600",
  };
  const labels = {
    psgc_match: "Match",
    psgc_mismatch: "Mismatch",
    psgc_no_validation: "N/A",
  };
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${styles[validation] || "bg-gray-100 text-gray-600"}`}>
      {labels[validation] || validation}
    </span>
  );
}

function EnrollmentBadge({ status }) {
  if (!status) return <span className="text-gray-400">—</span>;
  if (status === "active") {
    return <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-green-50 text-green-700">Active</span>;
  }
  return <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700">No enrollment</span>;
}

export default function SchoolTable({ schools, onSelect, selectedId }) {
  if (schools.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-sm text-[var(--muted-foreground)] gap-2">
        <MapPin className="h-8 w-8 opacity-30" />
        <span>Search by name or select a region to see schools</span>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 text-xs text-[var(--muted-foreground)] border-b border-[var(--border)] shrink-0 bg-[var(--secondary)]">
        {schools.length.toLocaleString()} school{schools.length !== 1 ? "s" : ""}
        {" "}({schools.filter(s => s.latitude != null).length.toLocaleString()} with coordinates)
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[var(--card)] z-10">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)] w-8"></th>
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)]">School ID</th>
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)]">School Name</th>
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)]">Sector</th>
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)]">Municipality</th>
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)]">Province</th>
              <th className="text-left px-3 py-2 font-medium text-[var(--muted-foreground)]">Region</th>
              <th className="text-center px-3 py-2 font-medium text-[var(--muted-foreground)]">PSGC</th>
              <th className="text-center px-3 py-2 font-medium text-[var(--muted-foreground)]">Enrollment</th>
            </tr>
          </thead>
          <tbody>
            {schools.map((school) => (
              <tr
                key={school.school_id}
                onClick={() => onSelect(school)}
                className={`border-b border-[var(--border)] cursor-pointer hover:bg-[var(--accent)] transition-colors ${
                  selectedId === school.school_id ? "bg-[var(--accent)]" : ""
                }`}
              >
                <td className="px-3 py-2 text-center">
                  <StatusDot school={school} />
                </td>
                <td className="px-3 py-2 font-mono text-[var(--muted-foreground)]">{school.school_id}</td>
                <td className="px-3 py-2 font-medium max-w-[200px] truncate">{school.school_name || "Unnamed"}</td>
                <td className="px-3 py-2">
                  <span className={school.sector === "public" ? "text-green-700" : "text-blue-700"}>
                    {school.sector}
                  </span>
                </td>
                <td className="px-3 py-2 text-[var(--muted-foreground)] max-w-[120px] truncate">{school.municipality || "—"}</td>
                <td className="px-3 py-2 text-[var(--muted-foreground)] max-w-[120px] truncate">{school.province || "—"}</td>
                <td className="px-3 py-2 text-[var(--muted-foreground)] max-w-[100px] truncate">{school.region || "—"}</td>
                <td className="px-3 py-2 text-center"><ValidationBadge validation={school.psgc_validation} /></td>
                <td className="px-3 py-2 text-center"><EnrollmentBadge status={school.enrollment_status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
