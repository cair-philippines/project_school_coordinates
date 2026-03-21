import { School, MapPin, Users, Building2 } from "lucide-react";

export default function StatsBar({ stats }) {
  if (!stats) return null;

  const items = [
    { icon: School, label: "Total Schools", value: stats.total_schools?.toLocaleString() },
    { icon: Building2, label: "Public", value: stats.public_schools?.toLocaleString() },
    { icon: Building2, label: "Private", value: stats.private_schools?.toLocaleString() },
    { icon: MapPin, label: "With Coords", value: stats.with_coordinates?.toLocaleString() },
    { icon: Users, label: "Active Enrollment", value: stats.active_enrollment?.toLocaleString() },
  ];

  return (
    <div className="flex items-center gap-4 overflow-x-auto text-xs">
      {items.map(({ icon: Icon, label, value }) => (
        <div key={label} className="flex items-center gap-1.5 shrink-0 text-[var(--muted-foreground)]">
          <Icon className="h-3.5 w-3.5" />
          <span className="font-medium text-[var(--foreground)]">{value}</span>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
