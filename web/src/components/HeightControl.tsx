export const MAX_HEIGHT = 250
const THUMB = 18

export type Ceiling = { label: string; metres: number }

/** Left offset that puts a marker under the slider thumb's centre for the same value. */
const at = (metres: number) => {
  const fraction = Math.max(0, Math.min(1, metres / MAX_HEIGHT))
  return `calc(${fraction * 100}% + ${(0.5 - fraction) * THUMB}px)`
}

/**
 * The one control that matters most: change the height and watch the answer change.
 * The marks come from the gate's own answer (the legal limit, and the ceiling of any
 * notice it cited), so the picture matches what the backend decided.
 */
export function HeightControl({ alt, error, ceilings, onChange, onBlur }: {
  alt: number
  error?: string
  ceilings: Ceiling[]
  onChange: (alt: number) => void
  onBlur: () => void
}) {
  const finite = Number.isFinite(alt)
  const value = finite ? Math.max(0, Math.min(MAX_HEIGHT, alt)) : 0
  const above = ceilings.filter((_, i) => i % 2 === 0)
  const below = ceilings.filter((_, i) => i % 2 === 1)

  return (
    <div className="panel p-4 space-y-2">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor="height-slider" className="text-sm font-medium text-ink-200">Flying height</label>
        <label className="flex items-center gap-1.5 text-xs text-ink-500">
          <input
            name="alt" type="number" inputMode="numeric"
            className="field !w-20 text-right" aria-label="Flying height in metres"
            aria-invalid={!!error} aria-describedby={error ? 'err-alt' : undefined}
            value={finite ? alt : ''} onBlur={onBlur}
            onChange={e => onChange(e.target.value === '' ? NaN : parseInt(e.target.value, 10))} />
          m above ground
        </label>
      </div>

      <div className="relative pt-5 pb-5">
        <input
          id="height-slider" type="range" min={0} max={MAX_HEIGHT} step={1}
          className="range" value={value}
          aria-valuetext={`${value} metres above ground`}
          style={{ '--fill': `${(value / MAX_HEIGHT) * 100}%` } as React.CSSProperties}
          onChange={e => onChange(parseInt(e.target.value, 10))} />
        {above.map(mark => (
          <span key={mark.label} aria-hidden
                className="absolute top-0 -translate-x-1/2 text-[11px] leading-none text-ink-400 whitespace-nowrap"
                style={{ left: at(mark.metres) }}>
            {mark.label} <span className="font-mono">{mark.metres} m</span>
            <span className="block mx-auto mt-1 w-px h-2 bg-ink-400" />
          </span>
        ))}
        {below.map(mark => (
          <span key={mark.label} aria-hidden
                className="absolute bottom-0 -translate-x-1/2 text-[11px] leading-none text-ink-400 whitespace-nowrap"
                style={{ left: at(mark.metres) }}>
            <span className="block mx-auto mb-1 w-px h-2 bg-ink-400" />
            {mark.label} <span className="font-mono">{mark.metres} m</span>
          </span>
        ))}
      </div>

      {error
        ? <p id="err-alt" className="text-xs text-rose-300">{error}</p>
        : <p className="text-xs text-ink-500">Drag the slider, then pause. The answer updates by itself.</p>}
    </div>
  )
}
