import { useEffect, useRef, useState } from 'react'
import { AdvancedOptions } from './components/AdvancedOptions'
import { DecisionPanel, EmptyState } from './components/DecisionPanel'
import { DroneIcon } from './components/DroneIcon'
import { Hero } from './components/Hero'
import { HeightControl, type Ceiling } from './components/HeightControl'
import { Learn } from './components/Learn'
import { MapView } from './components/MapView'
import { ScenarioCards } from './components/ScenarioCards'
import {
  ApiError, health, listNotams, validateFlight,
  type Decision, type FlightPlan, type Notam,
} from './lib/api'
import { planKey, validatePlan } from './lib/plan'
import { SCENARIOS, type Scenario } from './lib/scenarios'
import { useFormErrors } from './lib/useFormErrors'

const DEV = import.meta.env.DEV
const GITHUB = 'https://github.com/maczeo11/notam-guard'

/** DGCA CAR section 3 clause 7: the height limit for a micro drone. */
const LEGAL_LIMIT_M = 120

/** How long to wait after the last change before checking again, so dragging does not send a request per pixel. */
const RECHECK_DELAY_MS = 450

/** A visitor can link straight to an example with ?case=breach. Otherwise the first one runs. */
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
  /** Notices the gate has cited at one position, kept while the pin stays there so the mark survives going under the ceiling. */
  const [cited, setCited] = useState<{ at: string; refs: string[] }>()
  const decisionRef = useRef<HTMLDivElement>(null)
  const planRef = useRef(plan)               // the latest plan, so two quick changes cannot overwrite each other
  const latest = useRef(0)
  const timer = useRef<number>()
  const started = useRef(false)
  const form = useFormErrors(plan)

  useEffect(() => {
    listNotams().then(r => setNotams(r.notams || [])).catch(() => setNotams([]))
    health().then(r => setApi({ ok: true, version: r.version })).catch(() => setApi({ ok: false }))
    return () => window.clearTimeout(timer.current)
  }, [])

  // Show an answer straight away, so a first-time visitor is not left with an empty panel.
  useEffect(() => {
    if (started.current) return
    started.current = true
    void run(first.plan, false)
  }, [])

  async function run(next: FlightPlan, scroll: boolean) {
    const mine = ++latest.current           // ignore a slow reply to an older request
    setLoading(true)
    setError(undefined)
    try {
      const result = await validateFlight({ ...next, drone_id: next.drone_id.trim() })
      if (mine !== latest.current) return
      setDecision(result)
      setDecidedFor(planKey(next))
      const at = `${next.lat},${next.lon}`
      setCited(previous => ({
        at,
        refs: [...new Set([...(previous?.at === at ? previous.refs : []), ...(result.citations ?? [])])],
      }))
      if (scroll && window.matchMedia('(max-width: 1023px)').matches) {
        // On a phone the answer sits below the map, so bring it into view.
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

  /** Check again shortly, unless the plan has a field the gate would reject. */
  function schedule(next: FlightPlan) {
    window.clearTimeout(timer.current)
    if (Object.keys(validatePlan(next)).length > 0) return
    timer.current = window.setTimeout(() => void run(next, false), RECHECK_DELAY_MS)
  }

  function pickScenario(scenario: Scenario) {
    window.clearTimeout(timer.current)
    planRef.current = scenario.plan
    setScenarioId(scenario.id)
    setPlan(scenario.plan)
    window.history.replaceState(null, '', `?case=${scenario.id}`)
    void run(scenario.plan, true)
  }

  function patch(update: Partial<FlightPlan>) {
    const next = { ...planRef.current, ...update }
    planRef.current = next
    setScenarioId(undefined)
    if (window.location.search) window.history.replaceState(null, '', window.location.pathname)
    setPlan(next)
    schedule(next)
  }

  /** An explicit check: reveals any field errors, and otherwise runs now. */
  function check() {
    if (!form.submit()) return
    window.clearTimeout(timer.current)
    void run(plan, false)
  }

  const changed = decision !== null && decidedFor !== planKey(plan)
  const invalid = changed && form.hasErrors
  const updating = changed && !form.hasErrors
  const failure = error ? explain(error) : undefined

  // Marks on the height slider come from the gate's own answer, not from a second copy of the geometry.
  const ceilings: Ceiling[] = [
    { label: 'Legal limit', metres: LEGAL_LIMIT_M },
    ...(cited?.at === `${plan.lat},${plan.lon}` ? cited.refs : [])
      .map(ref => notams.find(n => n.id === ref))
      .filter((n): n is Notam => !!n && n.max_alt_m !== null && n.max_alt_m > 0)
      .map(n => ({ label: n.id, metres: n.max_alt_m as number })),
  ]

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-ink-800 px-5 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <DroneIcon className="w-9 h-9 shrink-0 text-ink-200" spinning={loading} />
            <div className="min-w-0">
              <div className="font-mono text-sm font-semibold tracking-[0.16em] text-ink-200">NOTAM&#8209;GUARD</div>
              <div className="text-[11px] text-ink-500 leading-tight hidden sm:block">A pre-flight check for drone flights</div>
            </div>
            <span className="font-mono text-[11px] px-1.5 py-0.5 rounded border border-ink-700 text-ink-400 whitespace-nowrap hidden md:inline">
              prototype · sample data
            </span>
          </div>
          <div className="flex items-center gap-4 font-mono text-[11px] text-ink-500">
            <span className="flex items-center gap-1.5" role="status">
              <span className={`w-1.5 h-1.5 rounded-full
                ${api === undefined ? 'bg-ink-700' : api.ok ? 'bg-emerald-400' : 'bg-rose-400'}`} aria-hidden />
              {api === undefined ? 'connecting' : api.ok ? 'online' : 'offline'}
            </span>
            <a className="hover:text-ink-200 transition-colors focus-ring rounded" href={GITHUB}>GitHub</a>
          </div>
        </div>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-5 py-7 space-y-7">
        <Hero />
        <ScenarioCards activeId={scenarioId} onPick={pickScenario} />

        {/* On a phone everything stacks in the order below, so the height slider sits just above its answer.
            On a wide screen the map and options form the left column, and the height and answer the right. */}
        <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[1.15fr_1fr] lg:gap-5 lg:items-start">
          <div className="contents lg:block lg:space-y-4">
            <div className="order-1">
              <MapView
                notams={notams}
                lat={plan.lat}
                lon={plan.lon}
                verdict={decision?.verdict}
                onPick={(lat, lon) => patch({ lat: +lat.toFixed(5), lon: +lon.toFixed(5) })} />
            </div>
            <div className="order-4">
              <AdvancedOptions
                plan={plan} loading={loading}
                shown={form.shown} touch={form.touch}
                onChange={patch} onSubmit={check} />
            </div>
          </div>

          <div className="contents lg:block lg:space-y-4">
            <div className="order-2">
              <HeightControl
                alt={plan.alt}
                error={form.shown('alt')}
                ceilings={ceilings}
                onChange={alt => patch({ alt })}
                onBlur={() => form.touch('alt')} />
            </div>
            <div ref={decisionRef} className="order-3 space-y-4 scroll-mt-4">
              {failure && (
                <div className="panel border-rose-900/70 bg-rose-950/30 px-4 py-3 space-y-2" role="alert">
                  <div className="label !text-rose-300">{failure.title}</div>
                  <p className="text-sm text-ink-200">{failure.body}</p>
                  <button
                    onClick={() => void run(plan, false)}
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
                    updating={updating}
                    invalid={invalid}
                    onRecheck={check}
                    onApproved={(ticketId, approver) =>
                      setApprovals(current => ({ ...current, [ticketId]: approver }))} />
                : !failure && <EmptyState loading={loading} />}
            </div>
          </div>
        </div>

        <Learn />
      </main>

      <footer className="border-t border-ink-800 px-5 py-4">
        <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 text-xs text-ink-500">
          <span>
            A prototype on sample data (four DGCA clauses, three notices). Not for planning real flights.
          </span>
          <a className="hover:text-ink-200 transition-colors font-mono focus-ring rounded"
             href={GITHUB}>github.com/maczeo11/notam-guard</a>
        </div>
      </footer>
    </div>
  )
}
