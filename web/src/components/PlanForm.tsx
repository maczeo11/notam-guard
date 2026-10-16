import { useRef, useState } from 'react'
import type { FlightPlan } from '../lib/api'
import { validatePlan, type PlanErrors } from '../lib/plan'

type Field = keyof PlanErrors

export function PlanForm({ plan, loading, onChange, onSubmit }: {
  plan: FlightPlan
  loading: boolean
  onChange: (patch: Partial<FlightPlan>) => void
  onSubmit: () => void
}) {
  const [touched, setTouched] = useState<Set<Field>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  const errors = validatePlan(plan)

  const shown = (field: Field) => (submitted || touched.has(field) ? errors[field] : undefined)
  const touch = (field: Field) => setTouched(current => new Set(current).add(field))
  const number = (value: string, parse: (s: string) => number) => (value === '' ? NaN : parse(value))
  const show = (value: number) => (Number.isNaN(value) ? '' : value)

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitted(true)
    const [firstInvalid] = Object.keys(errors)   // validatePlan adds keys in on-screen order
    if (firstInvalid) {
      // Read from `errors`, not from aria-invalid: that attribute only updates after this render.
      formRef.current?.querySelector<HTMLElement>(`[name="${firstInvalid}"]`)?.focus()
      return
    }
    onSubmit()
  }

  const input = (field: Field, label: string, props: React.InputHTMLAttributes<HTMLInputElement>) => (
    <label className="space-y-1 block">
      <span className="label">{label}</span>
      <input
        className="field"
        name={field}
        aria-invalid={!!shown(field)}
        aria-describedby={shown(field) ? `err-${field}` : undefined}
        onBlur={() => touch(field)}
        {...props} />
      {shown(field) && <p id={`err-${field}`} className="text-xs text-rose-300">{errors[field]}</p>}
    </label>
  )

  return (
    <form ref={formRef} className="panel p-3 space-y-3" onSubmit={submit} noValidate>
      <div className="grid grid-cols-3 gap-2">
        {input('lat', 'Lat', {
          type: 'number', step: 'any', inputMode: 'decimal', value: show(plan.lat),
          onChange: e => onChange({ lat: number(e.target.value, parseFloat) }),
        })}
        {input('lon', 'Lon', {
          type: 'number', step: 'any', inputMode: 'decimal', value: show(plan.lon),
          onChange: e => onChange({ lon: number(e.target.value, parseFloat) }),
        })}
        {input('alt', 'Altitude m', {
          type: 'number', inputMode: 'numeric', value: show(plan.alt),
          onChange: e => onChange({ alt: number(e.target.value, parseInt) }),
        })}
      </div>
      <p className="text-xs text-ink-500 -mt-1">
        Position comes from the map: click or tap it to move the plan. Altitude is metres above ground.
      </p>

      {input('drone_id', 'Drone', {
        value: plan.drone_id, maxLength: 64, autoComplete: 'off',
        onChange: e => onChange({ drone_id: e.target.value }),
      })}

      <label className="space-y-1 block">
        <span className="label">Request — read by the router</span>
        <textarea
          className="field !text-xs resize-y"
          name="query"
          rows={2} maxLength={500}
          aria-invalid={!!shown('query')}
          aria-describedby="hint-query"
          value={plan.query}
          onBlur={() => touch('query')}
          onChange={e => onChange({ query: e.target.value })} />
        <p id="hint-query" className="text-xs text-ink-500 leading-snug">
          Mention a rule or NOTAM (for example “DGCA CAR §7”) to run the full check. Without one, the gate
          validates the plan but holds it as unchecked, because nothing backs the answer.
        </p>
      </label>

      <button
        type="submit"
        disabled={loading}
        className="w-full font-mono text-xs uppercase tracking-[0.14em] py-2.5 rounded
                   bg-ink-200 text-ink-950 hover:bg-white disabled:opacity-50
                   disabled:cursor-not-allowed transition-colors focus-ring">
        {loading ? 'Evaluating…' : 'Validate plan'}
      </button>
    </form>
  )
}
