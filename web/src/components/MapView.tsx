import { MapContainer, TileLayer, Circle, Marker, Tooltip, useMapEvents, useMap } from 'react-leaflet'
import { useEffect, useMemo } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Notam, Verdict } from '../lib/api'
import { VERDICT_THEME } from '../lib/verdict'

const RING = {
  restrictive: '#fb7185',
  advisory: '#38bdf8',
}

const PIN: Record<string, string> = {
  ALLOW: 'pin-allow',
  BLOCK: 'pin-block',
  HOLD: 'pin-hold',
  ERROR: 'pin-none',
}

function ClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: e => onPick(e.latlng.lat, e.latlng.lng) })
  return null
}

/** Pan to the pin only when it has left the view, so dropping it does not make the map jump. */
function Follow({ lat, lon }: { lat: number; lon: number }) {
  const map = useMap()
  useEffect(() => {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    if (!map.getBounds().pad(-0.15).contains([lat, lon])) {
      map.flyTo([lat, lon], map.getZoom(), { duration: 0.6 })
    }
  }, [lat, lon, map])
  return null
}

export function MapView({ notams, lat, lon, verdict, onPick }: {
  notams: Notam[]
  lat: number
  lon: number
  verdict?: Verdict
  onPick: (lat: number, lon: number) => void
}) {
  // Only notices the parser could place are drawn. The rest are named below the
  // map rather than given an invented position.
  const drawable = notams.filter(n => n.geolocatable && n.lat !== null && n.lon !== null)
  const unplaceable = notams.filter(n => !n.geolocatable)
  const placed = Number.isFinite(lat) && Number.isFinite(lon)

  // The pin is styled by class only: an inline style attribute would be blocked by the CSP.
  const icon = useMemo(() => L.divIcon({
    className: `pin ${PIN[verdict ?? 'ERROR'] ?? PIN.ERROR}`,
    html: '<span class="pin-core"></span>',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  }), [verdict])

  return (
    <div className="panel overflow-hidden" role="region"
         aria-label="Map of airspace restrictions. Drag the pin or tap the map to move the flight.">
      <MapContainer center={[18.535, 73.85]} zoom={13} className="h-[260px] sm:h-[420px] lg:h-[500px] w-full" scrollWheelZoom>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
          className="dark-tiles" />
        <ClickHandler onPick={onPick} />
        <Follow lat={lat} lon={lon} />

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
              {notam.id} · {notam.severity === 'restrictive' ? 'restricted' : 'caution'}
              {notam.max_alt_m !== null ? ` · max ${notam.max_alt_m} m` : ' · no stated limit'}
            </Tooltip>
          </Circle>
        ))}

        {placed && (
          <Marker
            position={[lat, lon]}
            icon={icon}
            draggable
            eventHandlers={{
              dragend: event => {
                const point = (event.target as L.Marker).getLatLng()
                onPick(point.lat, point.lng)
              },
            }}>
            <Tooltip permanent direction="top" offset={[0, -16]}>
              {VERDICT_THEME[verdict ?? 'ERROR']?.headline ?? 'Your flight'}
            </Tooltip>
          </Marker>
        )}
      </MapContainer>

      <div className="px-3.5 py-2.5 border-t border-ink-800 space-y-1.5">
        <p className="text-xs text-ink-200">
          <strong className="font-medium">Drag the pin</strong>, or tap anywhere on the map, to move the drone.
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-400">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-full border" style={{ borderColor: RING.restrictive }} />
            Red circle: a height limit or no-go area
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="w-2.5 h-2.5 rounded-full border" style={{ borderColor: RING.advisory }} />
            Blue circle: caution only
          </span>
        </div>
        {unplaceable.length > 0 && (
          <p className="text-xs text-amber-300/90"
             title="The notice states a restriction but no usable location, so it cannot be drawn.">
            {unplaceable.map(n => n.id).join(', ')} can't be drawn: the notice gives no location.
          </p>
        )}
      </div>
    </div>
  )
}
