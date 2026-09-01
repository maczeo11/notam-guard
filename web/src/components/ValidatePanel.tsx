import { useState } from 'react'
import { validateFlight } from '../lib/api'

export function ValidatePanel({ lat, lon }:{ lat:number, lon:number }){
  const [alt,setAlt]=useState(120); const [drone,setDrone]=useState('D12'); const [res,setRes]=useState<any>(null); const [loading,setLoading]=useState(false)
  async function go(){ setLoading(true); try{ const r=await validateFlight(lat,lon,alt,drone); setRes(r)} catch(e:any){ setRes({verdict:'ERROR', reason:String(e)})} setLoading(false)}
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <input value={lat} readOnly className="bg-slate-800 rounded px-2 py-1 text-sm" />
        <input value={lon} readOnly className="bg-slate-800 rounded px-2 py-1 text-sm" />
        <input type="number" value={alt} onChange={e=>setAlt(parseInt(e.target.value)||0)} className="bg-slate-800 rounded px-2 py-1 text-sm" placeholder="alt" />
      </div>
      <input value={drone} onChange={e=>setDrone(e.target.value)} className="w-full bg-slate-800 rounded px-2 py-1 text-sm" placeholder="drone_id" />
      <button onClick={go} disabled={loading} className="w-full bg-cyan-600 hover:bg-cyan-500 rounded py-2 text-sm font-medium">{loading?'Checking...':'Validate /validate'}</button>
      {res && (
        <div className={`rounded p-3 text-sm ${res.verdict==='BLOCK'?'bg-amber-950 border border-amber-800 text-amber-200':'bg-emerald-950 border border-emerald-800 text-emerald-200'}`}>
          <div className="font-bold">{res.verdict} {res.requires_human && '• HOLD human gate'}</div>
          <div className="text-xs opacity-80">{res.reason}</div>
          <div className="flex gap-1 mt-2 flex-wrap">{(res.citations||[]).map((c:string)=><span key={c} className="bg-slate-800 px-2 py-0.5 rounded text-xs border border-slate-700">{c}</span>)}</div>
          {res.ticket_id && <div className="text-xs mt-1">Ticket {res.ticket_id} 1/49 idempotent</div>}
        </div>
      )}
    </div>
  )
}
