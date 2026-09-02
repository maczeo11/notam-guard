import { useEffect, useState } from 'react'
import { DecisionPanel, EmptyState } from './components/DecisionPanel'
import { MapView } from './components/MapView'
import { PlanForm } from './components/PlanForm'
import { ScenarioBar } from './components/ScenarioBar'
import { health, listNotams, validateFlight, type Decision, type FlightPlan, type Notam } from './lib/api'
import { SCENARIOS, type Scenario } from './lib/scenarios'

export default function App() {
  const [plan, setPlan] = useState<FlightPlan>(SCENARIOS[0].plan)
  const [scenarioId, setScenarioId] = useState<string | undefined>()
  const [decision, setDecision] = useState<Decision | null>(null)
  const [error, setError] = useState<string>()
  const [loading, setLoading] = useState(false)
  const [notams, setNotams] = useState<Notam[]>([])
  const [version, setVersion] = useState<string>()

  useEffect(() => {
    listNotams().then(r => setNotams(r.notams)).catch(() => setNotams([]))
    health().then(r => setVersion(r.version)).catch(() => setVersion(undefined))
  }, [])

  async function run(next: FlightPlan) {
    setLoading(true)
    setError(undefined)
    try {
      setDecision(await validateFlight(next))
    } catch (e) {
      setDecision(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function pickScenario(scenario: Scenario) {
    setScenarioId(scenario.id)
    setPlan(scenario.plan)
    run(scenario.plan)
  }

  function patch(update: Partial<FlightPlan>) {
    setScenarioId(undefined)
    setPlan(current => ({ ...current, ...update }))
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-ink-800 px-5 py-3.5">
        <div className="max-w-6xl mx-auto flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="font-mono text-sm font-semibold tracking-[0.18em]">NOTAM&#8209;GUARD</h1>
            <p className="text-xs text-ink-500 mt-0.5">
              Decides whether a drone flight plan may launch — and refuses to guess.
            </p>
          </div>
          <div className="font-mono text-[11px] text-ink-500 tabular">
            {notams.length} NOTAMs{version ? ` · api ${version}` : ''}
          </div>
        </div>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-5 py-5 space-y-4">
        <ScenarioBar activeId={scenarioId} onPick={pickScenario} />

        <div className="grid lg:grid-cols-[1.35fr_1fr] gap-4 items-start">
          <div className="space-y-4">
            <MapView
              notams={notams}
              lat={plan.lat}
              lon={plan.lon}
              verdict={decision?.verdict}
              onPick={(lat, lon) => patch({ lat: +lat.toFixed(5), lon: +lon.toFixed(5) })} />
            <PlanForm plan={plan} loading={loading} onChange={patch} onSubmit={() => run(plan)} />
          </div>

          <div className="space-y-4 lg:sticky lg:top-5">
            {error && (
              <div className="panel border-rose-900/70 bg-rose-950/30 px-4 py-3">
                <div className="label">Request failed</div>
                <p className="font-mono text-[11px] text-rose-300 mt-1 break-all">{error}</p>
                <p className="text-[11px] text-ink-500 mt-2">
                  Is the API running on :8000? Start it with{' '}
                  <span className="font-mono">uvicorn src.app:app --port 8000</span>.
                </p>
              </div>
            )}
            {decision ? <DecisionPanel decision={decision} /> : !error && <EmptyState />}
          </div>
        </div>
      </main>

      <footer className="border-t border-ink-800 px-5 py-3">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-500">
          <span>Verdicts come from deterministic geometry, never from the language model.</span>
          <a className="hover:text-ink-200 transition-colors font-mono"
             href="https://github.com/maczeo11/notam-guard">github.com/maczeo11/notam-guard</a>
        </div>
      </footer>
    </div>
  )
}
