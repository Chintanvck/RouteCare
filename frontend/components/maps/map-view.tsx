"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

export interface MapMarkerData {
  key: string;
  type: "patient" | "therapist";
  label: string;
  sublabel?: string;
  latitude: number;
  longitude: number;
}

// Leaflet's default marker icons resolve to relative image paths that break under Next.js's
// bundler - simple colored circles avoid that entirely (no marker PNG assets to wire up) and
// double as an easy visual distinction between patients, therapists, and the selected marker.
function makeCircleIcon(color: string, size: number): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${color};border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.45);"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

const PATIENT_ICON = makeCircleIcon("#2563eb", 14);
const THERAPIST_ICON = makeCircleIcon("#16a34a", 14);
const SELECTED_ICON = makeCircleIcon("#dc2626", 20);

const DEFAULT_CENTER: [number, number] = [40.7128, -74.006];

interface MapViewProps {
  markers: MapMarkerData[];
  selectedKey: string | null;
  onSelect: (marker: MapMarkerData) => void;
}

export function MapView({ markers, selectedKey, onSelect }: MapViewProps) {
  const center: [number, number] =
    markers.length > 0
      ? [
          markers.reduce((sum, m) => sum + m.latitude, 0) / markers.length,
          markers.reduce((sum, m) => sum + m.longitude, 0) / markers.length,
        ]
      : DEFAULT_CENTER;

  return (
    <MapContainer center={center} zoom={markers.length > 0 ? 11 : 8} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {markers.map((marker) => (
        <Marker
          key={marker.key}
          position={[marker.latitude, marker.longitude]}
          icon={marker.key === selectedKey ? SELECTED_ICON : marker.type === "patient" ? PATIENT_ICON : THERAPIST_ICON}
          eventHandlers={{ click: () => onSelect(marker) }}
        >
          <Popup>
            <p className="font-medium">{marker.label}</p>
            {marker.sublabel && <p className="text-muted-foreground">{marker.sublabel}</p>}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
