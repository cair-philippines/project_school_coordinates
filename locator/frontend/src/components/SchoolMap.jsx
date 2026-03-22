import { useEffect, useMemo, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap, LayersControl } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix default marker icons in bundled environments
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const PH_CENTER = [12.5, 122.0];
const PH_ZOOM = 6;

/**
 * PSGC-aware marker colors:
 *   Green — public, psgc_match
 *   Blue  — private, psgc_match
 *   Green pulsing — public, psgc_mismatch
 *   Blue pulsing  — private, psgc_mismatch
 *   Gray  — either sector, psgc_no_validation
 */
function createIcon(school) {
  const validation = school.psgc_validation;

  if (validation === "psgc_mismatch") {
    const color = school.sector === "public" ? "#22c55e" : "#3b82f6";
    const rgbaColor = school.sector === "public" ? "rgba(34,197,94,0.4)" : "rgba(59,130,246,0.4)";
    return L.divIcon({
      className: "",
      html: `<div style="position:relative; width:16px; height:16px;">
        <div style="
          position:absolute; top:2px; left:2px;
          width:12px; height:12px;
          background:${color};
          border:2px solid white;
          border-radius:50%;
          box-shadow:0 2px 4px rgba(0,0,0,0.3);
          z-index:2;
        "></div>
        <div style="
          position:absolute; top:0; left:0;
          width:16px; height:16px;
          border-radius:50%;
          background:${rgbaColor};
          animation:pulse-ring 2s ease-out infinite;
        "></div>
      </div>`,
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      popupAnchor: [0, -10],
    });
  }

  let color;
  if (validation === "psgc_match") {
    color = school.sector === "public" ? "#22c55e" : "#3b82f6";
  } else {
    // psgc_no_validation or null
    color = "#9ca3b8";
  }

  return L.divIcon({
    className: "",
    html: `<div style="
      width:12px; height:12px;
      background:${color};
      border:2px solid white;
      border-radius:50%;
      box-shadow:0 2px 4px rgba(0,0,0,0.3);
    "></div>`,
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    popupAnchor: [0, -8],
  });
}

/**
 * Compute robust bounding box, excluding spatial outliers.
 * Uses IQR (interquartile range) on lat and lon separately
 * to filter out stray points before computing bounds.
 */
function robustBounds(markers) {
  if (markers.length === 0) return null;
  if (markers.length <= 3) {
    return L.latLngBounds(markers.map((s) => [s.latitude, s.longitude]));
  }

  const lats = markers.map((s) => s.latitude).sort((a, b) => a - b);
  const lons = markers.map((s) => s.longitude).sort((a, b) => a - b);

  const q1Idx = Math.floor(lats.length * 0.25);
  const q3Idx = Math.floor(lats.length * 0.75);

  const latQ1 = lats[q1Idx], latQ3 = lats[q3Idx];
  const lonQ1 = lons[q1Idx], lonQ3 = lons[q3Idx];
  const latIQR = latQ3 - latQ1;
  const lonIQR = lonQ3 - lonQ1;

  // 2x IQR fence — generous enough to keep legitimate spread,
  // tight enough to exclude stray bad coordinates
  const latMin = latQ1 - 2 * latIQR;
  const latMax = latQ3 + 2 * latIQR;
  const lonMin = lonQ1 - 2 * lonIQR;
  const lonMax = lonQ3 + 2 * lonIQR;

  const inliers = markers.filter(
    (s) =>
      s.latitude >= latMin && s.latitude <= latMax &&
      s.longitude >= lonMin && s.longitude <= lonMax
  );

  // Fall back to all markers if IQR filtering removed too many
  const pts = inliers.length >= markers.length * 0.5 ? inliers : markers;
  return L.latLngBounds(pts.map((s) => [s.latitude, s.longitude]));
}

/**
 * Two independent effects:
 * 1. flyToTrigger — explicit "fly to this school" command, highest priority
 * 2. signature — markers changed from filter/search, fit bounds
 *
 * They don't interfere because flyToTrigger only fires on user click,
 * and signature only fires on filter/search result changes.
 */
function MapViewController({ selectedSchool, markers, mode, flyToTrigger }) {
  const map = useMap();
  const prevSignature = useRef("");
  const prevTrigger = useRef(0);

  const signature = useMemo(() => {
    if (markers.length === 0) return "empty";
    const first = markers[0]?.school_id || "";
    const last = markers[markers.length - 1]?.school_id || "";
    return `${markers.length}:${first}:${last}`;
  }, [markers]);

  // Effect 1: Explicit fly-to command (user clicked a school)
  useEffect(() => {
    if (flyToTrigger === prevTrigger.current) return;
    prevTrigger.current = flyToTrigger;
    if (!selectedSchool) return;

    // Stop any in-progress animation
    map.stop();

    if (selectedSchool.latitude && selectedSchool.longitude) {
      map.flyTo([selectedSchool.latitude, selectedSchool.longitude], 16, {
        duration: 1.2,
      });
    } else {
      // No coords — zoom to locality as best-effort
      const locality = selectedSchool.municipality || selectedSchool.province || selectedSchool.region;
      if (locality && markers.length > 0) {
        const field = selectedSchool.municipality ? "municipality"
          : selectedSchool.province ? "province" : "region";
        const nearby = markers.filter(
          (s) => s[field] && s[field].toLowerCase() === locality.toLowerCase()
        );
        if (nearby.length > 0) {
          const bounds = robustBounds(nearby);
          if (bounds && bounds.isValid()) {
            map.flyToBounds(bounds, { padding: [40, 40], maxZoom: 13, duration: 1.2 });
          }
        }
      }
    }
    // Update signature so Effect 2 doesn't re-zoom
    prevSignature.current = signature;
  }, [flyToTrigger, selectedSchool, markers, signature, map]);

  // Effect 2: Markers changed (filter/search results updated)
  useEffect(() => {
    if (signature === prevSignature.current) return;
    prevSignature.current = signature;

    if (signature === "empty") {
      map.flyTo(PH_CENTER, PH_ZOOM, { duration: 1.0 });
    } else if (mode !== "search") {
      const bounds = robustBounds(markers);
      if (bounds && bounds.isValid()) {
        map.flyToBounds(bounds, {
          padding: [40, 40],
          maxZoom: 15,
          duration: 1.2,
        });
      }
    }
  }, [signature, markers, mode, map]);

  return null;
}

const MAP_MARKER_CAP = 3000;

/**
 * Cap markers for rendering performance while preserving sector proportions.
 * If total exceeds the cap, sample each sector proportionally.
 */
function capMarkers(withCoords) {
  if (withCoords.length <= MAP_MARKER_CAP) return withCoords;

  const pub = withCoords.filter((s) => s.sector === "public");
  const priv = withCoords.filter((s) => s.sector === "private");
  const total = withCoords.length;

  const pubSlots = Math.round((pub.length / total) * MAP_MARKER_CAP);
  const privSlots = MAP_MARKER_CAP - pubSlots;

  // Evenly sample from each sector
  const sample = (arr, n) => {
    if (arr.length <= n) return arr;
    const step = arr.length / n;
    return Array.from({ length: n }, (_, i) => arr[Math.floor(i * step)]);
  };

  return [...sample(pub, pubSlots), ...sample(priv, privSlots)];
}

export default function SchoolMap({ schools, selectedSchool, mode = "idle", flyToTrigger = 0 }) {
  // All schools with coords — used for bounds calculation
  const allWithCoords = useMemo(() => {
    return schools.filter((s) => s.latitude && s.longitude);
  }, [schools]);

  // Capped subset for rendering markers
  const markers = useMemo(() => {
    return capMarkers(allWithCoords);
  }, [allWithCoords]);

  return (
    <MapContainer
      center={PH_CENTER}
      zoom={PH_ZOOM}
      className="h-full w-full rounded-xl"
      zoomControl={true}
      scrollWheelZoom={true}
    >
      <LayersControl position="bottomright">
        <LayersControl.BaseLayer checked name="Light">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="OpenStreetMap">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satellite">
          <TileLayer
            attribution='Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics'
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <MapViewController selectedSchool={selectedSchool} markers={allWithCoords} mode={mode} flyToTrigger={flyToTrigger} />
      {markers.map((school) => (
        <Marker
          key={school.school_id}
          position={[school.latitude, school.longitude]}
          icon={createIcon(school)}
        >
          <Popup className="custom-popup">
            <div className="p-3">
              <div className="font-semibold text-sm text-gray-900 leading-tight">
                {school.school_name || "Unnamed School"}
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {school.school_id} &middot;{" "}
                <span className={school.sector === "public" ? "text-blue-600" : "text-pink-600"}>
                  {school.sector}
                </span>
              </div>
              <div className="mt-2 text-xs text-gray-600 space-y-0.5">
                {school.barangay && <div>Brgy. {school.barangay}</div>}
                {school.municipality && <div>{school.municipality}</div>}
                {school.province && <div>{school.province}</div>}
                {school.region && <div>{school.region}</div>}
              </div>
              <div className="mt-2 pt-2 border-t border-gray-100 text-xs text-gray-400 space-y-0.5">
                <div>{school.latitude?.toFixed(6)}, {school.longitude?.toFixed(6)}</div>
                {school.coord_source && <div>Source: {school.coord_source}</div>}
                {school.enrollment_status && (
                  <div className={school.enrollment_status === "active" ? "text-green-600" : "text-amber-600"}>
                    Enrollment: {school.enrollment_status.replace(/_/g, " ")}
                  </div>
                )}
              </div>
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
