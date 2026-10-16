import type { FlightPlan } from '../lib/api'
import type { Field } from '../lib/useFormErrors'

/** Everything a first-time visitor does not need to touch, kept one click away. */
export function AdvancedOptions({ plan, loading, shown, touch, onChange, onSubmit }: {
  plan: FlightPlan
  loading: boolean
  shown: (field: Field) => string | undefined
  touch: (field: Field) => void
  onChange: (patch: Partial<FlightPlan>) => void
  onSubmit: () => void
}) {
  const numeric = (value: string) => (value === '' ? NaN : parseFloat(value))
  const show = (value: number) => (Number.isNaN(value) ? '' : value)

  const text = (field: Field, label: string, props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <label className="space-y-1 block">
      <span className="label">{label}</span>
      <input
        className="field" name={field}
        aria-invalid={!!shown(field)} aria-describedby={shown(field) ? `err-${field}` : undefined}
        onBlur={() => touch(field)} {...props} />
      {shown(field) && <p id={`err-${field}`} className="text-xs text-rose-300">{shown(field)}</p>}
    </label>
  )

  return (
    <details className="panel group">
      <summary className="px-4 py-3 cursor-pointer list-none flex items-center gap-2 hover:bg-ink-850 rounded-lg focus-ring">
        <span aria-hidden className="font-mono text-[11px] text-ink-500 group-open:rotate-90 transition-transform">▸</span>
        <span className="text-sm font-medium text-ink-200">More options</span>
        <span className="text-xs text-ink-500">exact position, drone name, request text</span>
      </summary>

      <form className="px-4 pb-4 space-y-3" noValidate
            onSubmit={event => { event.preventDefault(); onSubmit() }}>
        <div className="grid grid-cols-2 gap-2">
          {text('lat', 'Latitude', {
            type: 'number', step: 'any', inputMode: 'decimal', value: show(plan.lat),
            onChange: e => onChange({ lat: numeric(e.target.value) }),
          })}
          {text('lon', 'Longitude', {
            type: 'number', step: 'any', inputMode: 'decimal', value: show(plan.lon),
            onChange: e => onChange({ lon: numeric(e.target.value) }),
          })}
        </div>

        {text('drone_id', 'Drone name', {
          value: plan.drone_id, maxLength: 64, autoComplete: 'off',
          onChange: e => onChange({ drone_id: e.target.value }),
        })}

        <label className="space-y-1 block">
          <span className="label">Request text</span>
          <textarea
            className="field !text-xs resize-y" name="query" rows={2} maxLength={500}
            aria-invalid={!!shown('query')} aria-describedby="hint-query"
            value={plan.query} onBlur={() => touch('query')}
            onChange={e => onChange({ query: e.target.value })} />
          <p id="hint-query" className="text-xs text-ink-500 leading-snug">
            This is what the router reads. Mention a rule or notice (for example “DGCA CAR §7”) and the
            gate runs the full check. Without one it still checks the plan, but holds it, because nothing
            backs up the answer.
          </p>
        </label>

        <button type="submit" disabled={loading}
                className="w-full font-mono text-xs uppercase tracking-[0.14em] py-2.5 rounded
                           bg-ink-200 text-ink-950 hover:bg-white disabled:opacity-50
                           disabled:cursor-not-allowed transition-colors focus-ring">
          {loading ? 'Checking…' : 'Check this flight'}
        </button>
      </form>
    </details>
  )
}
