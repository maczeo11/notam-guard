const GATE = 0.75

/**
 * Draws confidence against the human-gate threshold. The point is not the
 * number but its position relative to the line: below it, nothing is cleared.
 */
export function ConfidenceMeter({ value, tone }: { value: number; tone: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  const below = value < GATE

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="label">Confidence</span>
        <span className={`font-mono text-sm tabular ${tone}`}>{value.toFixed(2)}</span>
      </div>

      <div className="relative h-1.5 rounded-full bg-ink-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${below ? 'bg-amber-400/80' : 'bg-emerald-400/80'}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="relative h-4">
        {/* The gate, drawn where it actually sits on the scale. */}
        <div className="absolute top-0 -translate-x-1/2 flex flex-col items-center" style={{ left: `${GATE * 100}%` }}>
          <div className="w-px h-1.5 bg-ink-500" />
          <span className="label !text-[9px] !tracking-normal whitespace-nowrap">gate {GATE}</span>
        </div>
      </div>

      <p className="text-[11px] leading-snug text-ink-500">
        {below
          ? 'Below the gate — an ALLOW is downgraded to HOLD and routed to a human.'
          : 'Above the gate — clear enough to authorise without review.'}
      </p>
    </div>
  )
}
