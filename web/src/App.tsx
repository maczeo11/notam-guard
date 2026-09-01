import { useState } from 'react'
import { MapView } from './components/MapView'
import { ValidatePanel } from './components/ValidatePanel'

export default function App(){
  const [pos,setPos]=useState({lat:18.53, lon:73.84})
  const [verdict,setVerdict]=useState<string>()
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4 flex justify-between items-center">
        <div><div className="font-bold tracking-widest text-sm">NOTAM-GUARD</div><div className="text-xs text-slate-400">DGCA CAR + NOTAM agentic gate — RAG pgvector 384d • Redis tile • LangSmith</div></div>
        <div className="text-xs bg-slate-900 border border-slate-800 px-3 py-1 rounded">p50 0.2ms p95 218ms • precision@3 1.00</div>
      </header>
      <main className="max-w-6xl mx-auto p-6 grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3"><MapView onPick={(lat,lon)=>setPos({lat,lon})} verdict={verdict} /></div>
        <div className="lg:col-span-2"><ValidatePanel lat={pos.lat} lon={pos.lon} /></div>
      </main>
      <footer className="text-center text-xs text-slate-500 py-4">Hexagonal ports: VectorStore / Memory / Ticket — swappable pgvector↔memory, Redis↔in-mem • Public repo github.com/maczeo11/notam-gaurd</footer>
    </div>
  )
}
