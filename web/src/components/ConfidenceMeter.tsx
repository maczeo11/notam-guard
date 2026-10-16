import type { Verdict } from '../lib/api'

const GATE = 0.75

const BAR: Record<string, string> = {
  ALLOW: 'bg-emerald-400/80',
  BLOCK: 'bg-rose-400/80',
  HOLD: 'bg-amber-400/80',
}

/** What the number means for this verdict. The gate only matters to an ALLOW. */
function caption(verdict: Verdict | undefined, value: number): string {
  if (verdict === 'BLOCK') {
    return 'A breach always goes to a person. The number shows how well the evidence backs the block.'
  }
  if (verdict === 'HOLD') {
    return value < GATE
      ? `Below the ${GATE.toFixed(2)} needed to clear, so a person must review it.`
      : 'A required check did not run, so a person must review it.'
  }
  return value >= GATE
    ? `At or above the ${GATE.toFixed(2)} needed to clear, so no person has to review it.`
    : `Below the ${GATE.toFixed(2)} needed to clear: this would be downgraded to a hold.`
}

/**
 * Draws confidence against the human-gate threshold. The point is not the
 * number but its position relative to the line, and what that means for the verdict.
 */
export function ConfidenceMeter({ value = 0, verdict, tone }: {
  value?: number
  verdict?: Verdict
  tone: string
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="label">How sure it is</span>
        <span className={`font-mono text-sm tabular ${tone}`}>{value.toFixed(2)}</span>
      </div>

      <div className="relative h-2 rounded-full bg-ink-800"
           role="meter" aria-label="Confidence" aria-valuemin={0} aria-valuemax={1} aria-valuenow={value}>
        <div
          className={`h-full rounded-full transition-all duration-500 ${BAR[verdict ?? 'ALLOW'] ?? BAR.ALLOW}`}
          style={{ width: `${pct}%` }}
        />
        {/* The gate, drawn where it actually sits on the scale. */}
        <div className="absolute -top-1 bottom-[-4px] w-0.5 bg-ink-200/80 rounded"
             style={{ left: `${GATE * 100}%` }} aria-hidden />
      </div>

      <div className="relative h-4" aria-hidden>
        <span className="absolute -translate-x-1/2 font-mono text-[11px] text-ink-400 whitespace-nowrap"
              style={{ left: `${GATE * 100}%` }}>
          {GATE.toFixed(2)} needed to clear
        </span>
      </div>

      <p className="text-xs leading-snug text-ink-500">{caption(verdict, value)}</p>
    </div>
  )
}
