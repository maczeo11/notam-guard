import { useEffect, useRef, useState } from 'react'
import { DecisionPanel, EmptyState } from './components/DecisionPanel'
import { MapView } from './components/MapView'
import { PlanForm } from './components/PlanForm'
import { ScenarioBar } from './components/ScenarioBar'
import {
  ApiError, health, listNotams, validateFlight,
  type Decision, type FlightPlan, type Notam,
} from './lib/api'
import { planKey } from './lib/plan'
import { SCENARIOS, type Scenario } from './lib/scenarios'

const DEV = import.meta.env.DEV

/** A visitor can link straight to a case with ?case=breach. Otherwise the first case runs. */
function startingScenario(): Scenario {
  const id = new URLSearchParams(window.location.search).get('case')
  return SCENARIOS.find(s => s.id === id) ?? SCENARIOS[0]
}

/** What went wrong, in words a visitor can act on. */
function explain(error: Error): { title: string; body: string } {
  const status = error instanceof ApiError ? error.status : -1
  if (status === 0 || status === 502 || status === 503 || status === 504 || status === 404) {
    return {
      title: 'The demo server is not responding',
      body: 'The page loaded, but its backend did not answer. It may be restarting. Try again in a moment.',
    }
  }
  if (status === 429) {
    return { title: 'Too many requests', body: 'Wait a few seconds and try again.' }
  }
  if (status === 422) {
    return { title: 'The plan was rejected', body: 'Check the values in the form and try again.' }
  }
  return { title: 'Something went wrong', body: 'The request failed. Try again.' }
}

export default function App() {
  const first = useRef(startingScenario()).current
  const [plan, setPlan] = useState<FlightPlan>(first.plan)
  const [scenarioId, setScenarioId] = useState<string | undefined>(first.id)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [decidedFor, setDecidedFor] = useState<string>()
  const [error, setError] = useState<Error>()
  const [loading, setLoading] = useState(false)
  const [notams, setNotams] = useState<Notam[]>([])
  const [api, setApi] = useState<{ ok: boolean; version?: string }>()
  const [approvals, setApprovals] = useState<Record<string, string>>({})
  const decisionRef = useRef<HTMLDivElement>(null)
  const latest = useRef(0)
  const started = useRef(false)

  useEffect(() => {
    listNotams().then(r => setNotams(r.notams || [])).catch(() => setNotams([]))
    health().then(r => setApi({ ok: true, version: r.version })).catch(() => setApi({ ok: false }))
  }, [])

  // Show a verdict straight away, so a first-time visitor is not left with an empty panel.
  useEffect(() => {
    if (started.current) return
    started.current = true
    void run(first.plan, false)
  }, [])

  async function run(next: FlightPlan, scroll = true) {
    const mine = ++latest.current           // ignore a slow reply to an older request
    setLoading(true)
    setError(undefined)
    try {
      const result = await validateFlight({ ...next, drone_id: next.drone_id.trim() })
      if (mine !== latest.current) return
      setDecision(result)
      setDecidedFor(planKey(next))
      if (scroll && window.matchMedia('(max-width: 1023px)').matches) {
        // On a phone the result sits below the map and the form, so bring it into view.
        requestAnimationFrame(() =>
          decisionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
      }
    } catch (e) {
      if (mine !== latest.current) return
      setDecision(null)
      setError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      if (mine === latest.current) setLoading(false)
    }
  }

  function pickScenario(scenario: Scenario) {
    setScenarioId(scenario.id)
    setPlan(scenario.plan)
    window.history.replaceState(null, '', `?case=${scenario.id}`)
    void run(scenario.plan)
  }

  function patch(update: Partial<FlightPlan>) {
    setScenarioId(undefined)
    if (window.location.search) window.history.replaceState(null, '', window.location.pathname)
    setPlan(current => ({ ...current, ...update }))
  }

  const stale = decision !== null && decidedFor !== planKey(plan)
  const failure = error ? explain(error) : undefined

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-ink-800 px-5 py-3.5">
        <div className="max-w-6xl mx-auto flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="font-mono text-sm font-semibold tracking-[0.18em]">NOTAM&#8209;GUARD</h1>
              <span className="font-mono text-[11px] px-1.5 py-0.5 rounded border border-ink-700 text-ink-400">
                prototype · sample data
              </span>
            </div>
            <p className="text-xs text-ink-500 mt-1">
              Decides whether a drone flight plan may launch, and holds anything it cannot check.
            </p>
          </div>
          <div className="flex items-center gap-3 font-mono text-[11px] text-ink-500 tabular">
            <span className="flex items-center gap-1.5" role="status">
              <span className={`w-1.5 h-1.5 rounded-full
                ${api === undefined ? 'bg-ink-700' : api.ok ? 'bg-emerald-400' : 'bg-rose-400'}`} aria-hidden />
              {api === undefined ? 'connecting' : api.ok ? `api ${api.version ?? ''}` : 'api offline'}
            </span>
            <span>{notams.length} NOTAMs</span>
            <a className="hover:text-ink-200 transition-colors focus-ring rounded"
               href="https://github.com/maczeo11/notam-guard">GitHub</a>
          </div>
        </div>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-5 py-5 space-y-4">
        <ScenarioBar activeId={scenarioId} onPick={pickScenario} />

        <details className="text-xs text-ink-500 group">
          <summary className="cursor-pointer list-none hover:text-ink-200 transition-colors focus-ring rounded w-fit">
            <span aria-hidden className="inline-block group-open:rotate-90 transition-transform mr-1">▸</span>
            How to read a result
          </summary>
          <ul className="mt-2 space-y-1.5 leading-relaxed max-w-3xl list-disc pl-5">
            <li><span className="text-emerald-300">ALLOW</span>: no rule is breached and the evidence is strong enough to clear the flight without a person reviewing it.</li>
            <li><span className="text-rose-300">BLOCK</span>: a ceiling or NOTAM restriction is breached. A person always reviews it.</li>
            <li><span className="text-amber-300">HOLD</span>: the gate could not check something, for example the regulations could not be retrieved. It refuses to guess.</li>
            <li>Confidence starts at 1.00 and drops for every restriction it could not check and every rule it could not find in the retrieved text. An ALLOW below the 0.75 gate becomes a HOLD.</li>
            <li>The row of steps under the verdict shows which ones ran for this request. The decision itself is made by plain Python; the language model only picks a route and words one sentence.</li>
          </ul>
        </details>

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

          <div ref={decisionRef} className="space-y-4 lg:sticky lg:top-5 scroll-mt-4">
            {failure && (
              <div className="panel border-rose-900/70 bg-rose-950/30 px-4 py-3 space-y-2" role="alert">
                <div className="label !text-rose-300">{failure.title}</div>
                <p className="text-sm text-ink-200">{failure.body}</p>
                <button
                  onClick={() => run(plan)}
                  className="font-mono text-xs px-3 py-1.5 rounded border border-ink-700
                             text-ink-200 hover:bg-ink-800 transition-colors focus-ring">
                  Try again
                </button>
                {error && (
                  <details className="text-xs text-ink-500">
                    <summary className="cursor-pointer hover:text-ink-200 focus-ring rounded w-fit">Technical details</summary>
                    <p className="font-mono mt-1 break-all">{error.message}</p>
                    {DEV && (
                      <p className="mt-1">
                        Local development: start the API with{' '}
                        <span className="font-mono">uvicorn src.app:app --port 8000</span>.
                      </p>
                    )}
                  </details>
                )}
              </div>
            )}
            {decision
              ? <DecisionPanel
                  key={decision.ticket_id || 'no-ticket'}
                  decision={decision}
                  approvedBy={decision.ticket_id ? approvals[decision.ticket_id] : undefined}
                  loading={loading}
                  stale={stale}
                  onApproved={(ticketId, approver) =>
                    setApprovals(current => ({ ...current, [ticketId]: approver }))} />
              : !failure && <EmptyState loading={loading} />}
          </div>
        </div>
      </main>

      <footer className="border-t border-ink-800 px-5 py-3">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 text-xs text-ink-500">
          <span>
            A prototype on sample data (four DGCA clauses, three NOTAMs). Not for planning real flights.
          </span>
          <a className="hover:text-ink-200 transition-colors font-mono focus-ring rounded"
             href="https://github.com/maczeo11/notam-guard">github.com/maczeo11/notam-guard</a>
        </div>
      </footer>
    </div>
  )
}
