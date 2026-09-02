import type { FlightPlan } from '../lib/api'

export function PlanForm({ plan, loading, onChange, onSubmit }: {
  plan: FlightPlan
  loading: boolean
  onChange: (patch: Partial<FlightPlan>) => void
  onSubmit: () => void
}) {
  return (
    <form
      className="panel p-3 space-y-3"
      onSubmit={event => { event.preventDefault(); onSubmit() }}>
      <div className="grid grid-cols-3 gap-2">
        <label className="space-y-1">
          <span className="label">Lat</span>
          <input className="field" type="number" step="any" value={plan.lat}
                 onChange={e => onChange({ lat: e.target.value === '' ? 0 : parseFloat(e.target.value) })} />
        </label>
        <label className="space-y-1">
          <span className="label">Lon</span>
          <input className="field" type="number" step="any" value={plan.lon}
                 onChange={e => onChange({ lon: e.target.value === '' ? 0 : parseFloat(e.target.value) })} />
        </label>
        <label className="space-y-1">
          <span className="label">Alt AGL m</span>
          <input className="field" type="number" value={plan.alt}
                 onChange={e => onChange({ alt: e.target.value === '' ? 0 : parseInt(e.target.value) })} />
        </label>
      </div>

      <label className="space-y-1 block">
        <span className="label">Drone</span>
        <input className="field" value={plan.drone_id}
               onChange={e => onChange({ drone_id: e.target.value })} />
      </label>

      <label className="space-y-1 block">
        <span className="label">Query — the router reads this</span>
        <input className="field !text-xs" value={plan.query}
               onChange={e => onChange({ query: e.target.value })} />
      </label>

      <button
        type="submit"
        disabled={loading}
        className="w-full font-mono text-xs uppercase tracking-[0.14em] py-2.5 rounded
                   bg-ink-200 text-ink-950 hover:bg-white disabled:opacity-40
                   disabled:cursor-not-allowed transition-colors">
        {loading ? 'Evaluating…' : 'Validate plan'}
      </button>
    </form>
  )
}
