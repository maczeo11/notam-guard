import { MapContainer, TileLayer, Circle, CircleMarker, Tooltip, useMapEvents, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import 'leaflet/dist/leaflet.css'
import type { Notam, Verdict } from '../lib/api'
import { VERDICT_THEME } from '../lib/verdict'

const RING = {
  restrictive: '#fb7185',
  advisory: '#38bdf8',
}

const MARKER: Record<string, string> = {
  ALLOW: '#34d399',
  BLOCK: '#fb7185',
  HOLD: '#fbbf24',
  ERROR: '#7c736e',
}

function ClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: e => onPick(e.latlng.lat, e.latlng.lng) })
  return null
}

function FlyTo({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap()
  useEffect(() => { map.flyTo([lat, lon], map.getZoom(), { duration: 0.6 }) }, [lat, lon, map])
  return null
}

export function MapView({ notams, lat, lon, verdict, onPick }: {
  notams: Notam[]
  lat: number
  lon: number
  verdict?: Verdict
  onPick: (lat: number, lon: number) => void
}) {

  // Only NOTAMs the parser could place are drawn. The rest are named below the
  // map rather than given an invented position.
  const drawable = notams.filter(n => n.geolocatable && n.lat !== null && n.lon !== null)
  const unplaceable = notams.filter(n => !n.geolocatable)
  const colour = MARKER[verdict ?? 'ERROR'] ?? MARKER.ERROR

  return (
    <div className="panel overflow-hidden">
      <MapContainer center={[18.535, 73.85]} zoom={13} style={{ height: 420 }} scrollWheelZoom>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
          className="dark-tiles" />
        <ClickHandler onPick={onPick} />
        <FlyTo lat={lat} lon={lon} />

        {drawable.map(notam => (
          <Circle
            key={notam.id}
            center={[notam.lat as number, notam.lon as number]}
            radius={(notam.radius_km ?? 0) * 1000}
            pathOptions={{
              color: RING[notam.severity as keyof typeof RING] ?? RING.advisory,
              weight: 1,
              fillOpacity: 0.07,
            }}>
            <Tooltip>
              {notam.id} · {notam.severity}
              {notam.max_alt_m !== null ? ` · max ${notam.max_alt_m}m` : ' · no stated limit'}
            </Tooltip>
          </Circle>
        ))}

        <CircleMarker
          center={[lat, lon]}
          radius={6}
          pathOptions={{ color: colour, fillColor: colour, fillOpacity: 0.9, weight: 2 }}>
          <Tooltip permanent direction="top" offset={[0, -8]}>
            {verdict ? VERDICT_THEME[verdict]?.label ?? 'flight plan' : 'flight plan'}
          </Tooltip>
        </CircleMarker>
      </MapContainer>

      <div className="px-3 py-2.5 border-t border-ink-800 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <span className="label">Click to reposition</span>
        <span className="flex items-center gap-1.5 text-[11px] text-ink-400">
          <span className="w-2.5 h-2.5 rounded-full border" style={{ borderColor: RING.restrictive }} />
          restrictive
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-ink-400">
          <span className="w-2.5 h-2.5 rounded-full border" style={{ borderColor: RING.advisory }} />
          advisory
        </span>
        {unplaceable.length > 0 && (
          <span className="text-[11px] text-amber-300/70 ml-auto truncate max-w-xs" title={unplaceable.map(n => n.id).join(', ')}>
            {unplaceable.map(n => n.id).join(', ')} not drawn — no coordinates
          </span>
        )}
      </div>
    </div>
  )
}
