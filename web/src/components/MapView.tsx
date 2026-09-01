import { MapContainer, TileLayer, Circle, Marker, Tooltip, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useState } from 'react'
import type { Notam } from '../lib/api'

const RING = {
  restrictive: '#f43f5e',
  advisory: '#38bdf8',
}

export function MapView({ notams, onPick, verdict }: {
  notams: Notam[]
  onPick: (lat: number, lon: number) => void
  verdict?: string
}) {
  const [pos, setPos] = useState<[number, number]>([18.53, 73.84])

  function ClickHandler() {
    useMapEvents({
      click(event) {
        setPos([event.latlng.lat, event.latlng.lng])
        onPick(event.latlng.lat, event.latlng.lng)
      },
    })
    return null
  }

  // Only NOTAMs the parser could place are drawn; the rest are reported in the
  // panel rather than given an invented position on the map.
  const drawable = notams.filter(n => n.geolocatable)

  return (
    <div className="rounded-xl overflow-hidden border border-slate-800">
      <MapContainer center={pos} zoom={13} style={{ height: 380 }}>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution="&copy; OpenStreetMap &copy; CARTO" />
        <ClickHandler />
        <Marker position={pos}>
          <Tooltip permanent direction="top">
            {verdict ?? 'click to place a flight'}
          </Tooltip>
        </Marker>
        {drawable.map(notam => (
          <Circle
            key={notam.id}
            center={[notam.lat as number, notam.lon as number]}
            radius={(notam.radius_km as number) * 1000}
            pathOptions={{
              color: RING[notam.severity as keyof typeof RING] ?? RING.advisory,
              fillOpacity: 0.12,
            }}>
            <Tooltip>
              {notam.id} · {notam.severity}
              {notam.max_alt_m !== null ? ` · max ${notam.max_alt_m}m` : ''}
            </Tooltip>
          </Circle>
        ))}
      </MapContainer>
      <div className="px-3 py-2 text-xs text-slate-400">
        Click the map to place a flight. Red rings are restrictive NOTAMs, blue are advisory.
      </div>
    </div>
  )
}
