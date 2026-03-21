import {
  X,
  MapPin,
  School,
  Eye,
  Users,
  GraduationCap,
  Info,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
} from "lucide-react";

function Badge({ children, variant = "default" }) {
  const styles = {
    default: "bg-gray-100 text-gray-700",
    blue: "bg-blue-50 text-blue-700",
    pink: "bg-pink-50 text-pink-700",
    green: "bg-green-50 text-green-700",
    amber: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
  };
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${styles[variant]}`}>
      {children}
    </span>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] font-medium text-[var(--muted-foreground)] uppercase tracking-wide flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, muted }) {
  if (!value && value !== 0) return null;
  return (
    <div className="flex justify-between items-start text-sm">
      <span className="text-[var(--muted-foreground)] text-xs shrink-0">{label}</span>
      <span className={`text-right ml-2 text-xs ${muted ? "text-[var(--muted-foreground)]" : "font-medium"}`}>
        {value}
      </span>
    </div>
  );
}

const SOURCE_LABELS = {
  monitoring_validated: "Monitoring (university-validated)",
  osmapaaralan: "OSMapaaralan (OSM community-mapped)",
  nsbi_2324: "NSBI SY 2023-2024 (official inventory)",
  geolocation_deped: "Geolocation DepEd (internal office)",
  tosf_self_reported: "TOSF (self-reported via Google Forms)",
};

const SOURCE_TRUST = {
  monitoring_validated: { level: "Highest", variant: "green", desc: "Validated by university team against satellite imagery and social media" },
  osmapaaralan: { level: "High", variant: "green", desc: "Community-mapped and reviewed through OSM's rigorous mapping process" },
  nsbi_2324: { level: "Moderate", variant: "amber", desc: "Official DepEd system, but dated and not field-validated" },
  geolocation_deped: { level: "Low", variant: "amber", desc: "Internal office revision, lowest priority among public sources" },
  tosf_self_reported: { level: "Variable", variant: "amber", desc: "Self-reported by school — may be inaccurate, swapped, or approximate" },
};

const MONITORING_SUB_LABELS = {
  OSMapaaralan: "Validator chose OSMapaaralan coordinates as correct",
  NSBI: "Validator chose NSBI coordinates as correct",
  "New coordinates": "Validator found new coordinates from external sources",
};

export default function SchoolDetail({ school, onClose }) {
  if (!school) return null;

  const isPublic = school.sector === "public";
  const hasCoords = school.latitude != null && school.longitude != null;
  const coordSource = school.coord_source || school.coord_status;
  const trust = SOURCE_TRUST[school.coord_source] || null;

  return (
    <div className="absolute inset-y-0 right-0 w-96 bg-[var(--card)] border-l border-[var(--border)] shadow-xl z-10 flex flex-col">
      {/* Header */}
      <div className="shrink-0 p-4 border-b border-[var(--border)] bg-gradient-to-b from-[var(--accent)] to-[var(--card)]">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant={isPublic ? "blue" : "pink"}>
                <School className="h-3 w-3" />
                {school.sector}
              </Badge>
              {school.enrollment_status === "active" ? (
                <Badge variant="green">
                  <CheckCircle2 className="h-3 w-3" />active
                </Badge>
              ) : (
                <Badge variant="amber">
                  <AlertCircle className="h-3 w-3" />no enrollment
                </Badge>
              )}
            </div>
            <h2 className="font-semibold text-base leading-tight">
              {school.school_name || "Unnamed School"}
            </h2>
            <div className="text-xs text-[var(--muted-foreground)] mt-1">
              ID: {school.school_id}
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 p-1 rounded-lg hover:bg-[var(--secondary)] transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Location */}
        <Section title="Location" icon={MapPin}>
          <div className="space-y-1">
            <Row label="Barangay" value={school.barangay} />
            <Row label="Municipality" value={school.municipality} />
            <Row label="Province" value={school.province} />
            <Row label="Region" value={school.region} />
            {hasCoords && (
              <Row
                label="Coordinates"
                value={`${school.latitude.toFixed(6)}, ${school.longitude.toFixed(6)}`}
              />
            )}
            {school.location_source && (
              <Row label="Location data from" value={school.location_source} muted />
            )}
          </div>
        </Section>

        {/* Coordinate Lineage */}
        <Section title="Coordinate Lineage" icon={Eye}>
          {hasCoords ? (
            <div className="space-y-2">
              <div className="rounded-lg border border-[var(--border)] p-3 space-y-2">
                <div className="text-xs font-medium">
                  {SOURCE_LABELS[school.coord_source] || school.coord_source || "Unknown source"}
                </div>
                {trust && (
                  <div className="flex items-center gap-2">
                    <Badge variant={trust.variant}>Trust: {trust.level}</Badge>
                  </div>
                )}
                {trust && (
                  <div className="text-[11px] text-[var(--muted-foreground)]">
                    {trust.desc}
                  </div>
                )}
                {school.monitoring_chosen_source && (
                  <div className="mt-2 pt-2 border-t border-[var(--border)]">
                    <div className="text-[11px] text-[var(--muted-foreground)] flex items-center gap-1">
                      <ArrowRight className="h-3 w-3" />
                      {MONITORING_SUB_LABELS[school.monitoring_chosen_source] ||
                        `Validator chose: ${school.monitoring_chosen_source}`}
                    </div>
                  </div>
                )}
              </div>

              {school.sources_available && (
                <div>
                  <div className="text-[11px] text-[var(--muted-foreground)] mb-1">
                    Available in {school.sources_available.split(",").length} source(s):
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {school.sources_available.split(",").map((src) => (
                      <Badge
                        key={src}
                        variant={src === school.coord_source ? "green" : "default"}
                      >
                        {src === school.coord_source && <CheckCircle2 className="h-3 w-3" />}
                        {src.trim()}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1">
              <div className="text-xs font-medium text-amber-800">No coordinates available</div>
              <div className="text-[11px] text-amber-700">
                {school.coord_rejection_reason === "no_submission"
                  ? "This school did not submit coordinates in the TOSF data collection."
                  : school.coord_rejection_reason === "not_in_lis"
                  ? "This school was found in enrollment data but is not in the LIS master list."
                  : school.coord_rejection_reason === "invalid"
                  ? "Submitted coordinates were invalid (non-numeric, out of range, or zero)."
                  : school.coord_rejection_reason === "out_of_bounds"
                  ? "Submitted coordinates fell outside the Philippines bounding box."
                  : school.sources_available === "enrollment_only"
                  ? "This school is known only from enrollment data — no coordinate source has data for it."
                  : "No coordinate source has data for this school."}
              </div>
            </div>
          )}

          {/* Private school coord_status */}
          {!isPublic && school.coord_status && (
            <div className="text-[11px] text-[var(--muted-foreground)]">
              Coord status: <b>{school.coord_status}</b>
              {school.coord_status === "fixed_swap" && (
                <span className="ml-1">(latitude and longitude were swapped in submission — auto-corrected)</span>
              )}
            </div>
          )}
        </Section>

        {/* GASTPE (private only) */}
        {!isPublic && (
          <Section title="GASTPE Participation" icon={GraduationCap}>
            <div className="space-y-1">
              <Row
                label="ESC"
                value={school.esc_participating === 1 ? "Participating" : "No"}
              />
              <Row
                label="SHS VP"
                value={school.shsvp_participating === 1 ? "Participating" : "No"}
              />
              <Row
                label="JDVP"
                value={school.jdvp_participating === 1 ? "Participating" : "No"}
              />
            </div>
          </Section>
        )}

        {/* Enrollment */}
        <Section title="Enrollment Status" icon={Users}>
          <div className="text-sm">
            {school.enrollment_status === "active" ? (
              <span className="text-green-700">Has reported enrollment in SY 2024-2025</span>
            ) : (
              <span className="text-amber-700">
                No reported enrollment in SY 2024-2025
              </span>
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}
