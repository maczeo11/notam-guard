import { MapContainer, TileLayer, Circle, Marker, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useState } from 'react'

export function MapView({ onPick, verdict }:{ onPick:(lat:number,lon:number)=>void, verdict?:string }){
  const [pos, setPos] = useState<[number,number]>([18.53,73.84])
  function Click(){ useMapEvents({click(e){ setPos([e.latlng.lat, e.latlng.lng]); onPick(e.latlng.lat, e.latlng.lng)}}); return null}
  const isBlock = verdict==='BLOCK'
  return (
    <div className="rounded-xl overflow-hidden border border-slate-800">
      <MapContainer center={pos} zoom={14} style={{height:360}}>
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OSM & Carto" />
        <Click />
        <Marker position={pos} />
        <Circle center={[18.53,73.84]} radius={1000} pathOptions={{color: isBlock? '#f59e0b':'#10b981', fillColor: isBlock? '#f59e0b':'#10b981', fillOpacity:0.2}} />
      </MapContainer>
      <div className="px-3 py-2 text-xs text-slate-400">Click map to set flight • Crane NOTAM 09/03 18.53,73.84 1km 100m • Tile geo memory per 100m</div>
    </div>
  )
}
