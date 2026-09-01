import { useEffect, useState } from 'react'
import { MapView } from './components/MapView'
import { ValidatePanel } from './components/ValidatePanel'
import { health, listNotams, type Notam } from './lib/api'

export default function App() {
  const [pos, setPos] = useState({ lat: 18.53, lon: 73.84 })
  const [verdict, setVerdict] = useState<string>()
  const [notams, setNotams] = useState<Notam[]>([])
  const [version, setVersion] = useState<string>()

  useEffect(() => {
    listNotams().then(r => setNotams(r.notams)).catch(() => setNotams([]))
    health().then(r => setVersion(r.version)).catch(() => setVersion(undefined))
  }, [])

  const unevaluable = notams.filter(n => n.severity === 'restrictive' && !n.geolocatable)

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4 flex justify-between items-center">
        <div>
          <div className="font-bold tracking-widest text-sm">NOTAM-GUARD</div>
          <div className="text-xs text-slate-400">
            Compliance gate for drone dispatch — DGCA CAR + NOTAM, grounded citations, human hold
          </div>
        </div>
        <div className="text-xs bg-slate-900 border border-slate-800 px-3 py-1 rounded text-slate-400">
          {notams.length} NOTAMs loaded{version ? ` · api ${version}` : ''}
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-6 grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 space-y-4">
          <MapView notams={notams} onPick={(lat, lon) => setPos({ lat, lon })} verdict={verdict} />
          {unevaluable.length > 0 && (
            <div className="text-xs border border-amber-900 bg-amber-950/40 text-amber-200 rounded-lg px-3 py-2">
              {unevaluable.length} restrictive NOTAM
              {unevaluable.length > 1 ? 's are' : ' is'} not drawn:{' '}
              {unevaluable.map(n => n.id).join(', ')} state a restriction but no usable
              coordinates, so they cannot be evaluated geometrically. Every decision
              carries this as a warning and a confidence penalty.
            </div>
          )}
        </div>
        <div className="lg:col-span-2">
          <ValidatePanel lat={pos.lat} lon={pos.lon} onVerdict={setVerdict} />
        </div>
      </main>

      <footer className="text-center text-xs text-slate-500 py-4">
        Verdicts come from deterministic geometry, never from the language model ·{' '}
        <a className="underline hover:text-slate-300" href="https://github.com/maczeo11/notam-guard">
          github.com/maczeo11/notam-guard
        </a>
      </footer>
    </div>
  )
}
