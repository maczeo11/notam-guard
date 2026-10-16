import { useState } from 'react'
import { approveTicket, type Decision, type Verdict } from '../lib/api'
import { routeCopy } from '../lib/route'
import { markMatches, VERDICT_THEME } from '../lib/verdict'
import { ConfidenceMeter } from './ConfidenceMeter'
import { Pipeline } from './Pipeline'

/** Colour is never the only signal: each verdict also has its own glyph. */
const GLYPH: Record<Verdict, string> = { ALLOW: '✓', BLOCK: '✕', HOLD: '!', ERROR: '?' }

function Section({ title, count, children }: {
  title: string
  count?: number
  children: React.ReactNode
}) {
  return (
    <section className="border-t border-ink-800 px-4 py-3 space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="label">{title}</h3>
        {count !== undefined && <span className="font-mono text-[11px] text-ink-500">{count}</span>}
      </div>
      {children}
    </section>
  )
}

export function EmptyState({ loading }: { loading: boolean }) {
  return (
    <div className="panel p-6 text-center space-y-2" aria-busy={loading}>
      <div className="font-mono text-xs uppercase tracking-[0.14em] text-ink-500">
        {loading ? 'Evaluating…' : 'No decision yet'}
      </div>
      <p className="text-sm text-ink-400 leading-relaxed max-w-sm mx-auto">
        Pick a case above, or enter a plan and validate it. The gate returns{' '}
        <span className="text-emerald-300">ALLOW</span>, <span className="text-rose-300">BLOCK</span> or{' '}
        <span className="text-amber-300">HOLD</span>, with the rule it relied on and the text that defines it.
      </p>
    </div>
  )
}

export function DecisionPanel({ decision, approvedBy, loading, stale, onApproved }: {
  decision: Decision
  approvedBy?: string
  loading: boolean
  stale: boolean
  onApproved: (ticketId: string, approver: string) => void
}) {
  const [approving, setApproving] = useState(false)
  const [approveError, setApproveError] = useState<string>()
  const theme = VERDICT_THEME[decision.verdict] ?? VERDICT_THEME.ERROR
  const refs = decision.citations ?? []
  const route = routeCopy(decision.action)

  async function approve() {
    if (!decision.ticket_id) return
    setApproving(true)
    setApproveError(undefined)
    try {
      const result = await approveTicket(decision.ticket_id, 'ops@console')
      onApproved(decision.ticket_id, result.approved_by || 'ops@console')
    } catch {
      setApproveError('Could not record the approval. Try again in a moment.')
    } finally {
      setApproving(false)
    }
  }

  return (
    <div className={`panel overflow-hidden animate-rise transition-opacity ${theme.border}
                     ${loading || stale ? 'opacity-60' : ''}`}
         aria-busy={loading}>
      {stale && !loading && (
        <div className="px-4 py-2 text-xs text-amber-300 bg-amber-950/40 border-b border-amber-900/60" role="status">
          You changed the plan. Press “Validate plan” to refresh this decision.
        </div>
      )}
      {loading && (
        <div className="px-4 py-2 text-xs text-ink-400 bg-ink-850 border-b border-ink-800" role="status">
          Evaluating…
        </div>
      )}

      {/* Verdict — the only saturated element on the page. */}
      <div className={`px-4 py-4 space-y-3 ${theme.bg}`}>
        <div className="flex items-center gap-2.5" role="status" aria-live="polite">
          <span className={`w-6 h-6 rounded-full border flex items-center justify-center
                            font-mono text-xs font-semibold ${theme.accent} ${theme.border}`} aria-hidden>
            {GLYPH[decision.verdict] ?? '?'}
          </span>
          <span className={`font-mono text-2xl font-semibold tracking-tight ${theme.accent}`}>
            {theme.label}
          </span>
        </div>

        <p className="text-xs text-ink-500 leading-snug">{theme.meaning}</p>
        <p className="text-sm text-ink-200 leading-relaxed">{decision.reason}</p>

        {typeof decision.confidence === 'number' && (
          <div className="pt-1">
            <ConfidenceMeter value={decision.confidence} verdict={decision.verdict} tone={theme.accent} />
          </div>
        )}

        <div className="pt-1 space-y-1.5">
          <div className="flex items-baseline gap-2">
            <span className="label">Route</span>
            <span className="font-mono text-xs text-ink-200">{route.name}</span>
          </div>
          <Pipeline action={decision.action} />
          {route.detail && <p className="text-xs text-ink-500 leading-snug">{route.detail}</p>}
        </div>
      </div>

      {decision.evidence?.length > 0 && (
        <Section title="Evidence" count={decision.evidence.length}>
          <div className="space-y-1.5">
            {decision.evidence.map(item => (
              <div key={item.ref}
                   className="bg-ink-850 border border-ink-800 rounded px-2.5 py-2 space-y-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className={`font-mono text-xs ${item.grounded ? 'text-emerald-300' : 'text-rose-300'}`}
                        aria-hidden>
                    {item.grounded ? '✓' : '✗'}
                  </span>
                  <span className="font-mono text-xs text-ink-200 whitespace-nowrap">{item.ref}</span>
                  <span className="label sm:ml-auto">
                    {item.grounded ? 'defined in retrieved text' : 'not found in retrieved text'}
                  </span>
                </div>
                {item.excerpt && (
                  <p className="text-xs leading-snug text-ink-500 pl-5">{item.excerpt}</p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {decision.retrieved?.length > 0 && (
        <details className="border-t border-ink-800 group">
          <summary className="px-4 py-3 cursor-pointer list-none flex items-baseline gap-2
                              hover:bg-ink-850 focus-ring">
            <span className="font-mono text-[11px] text-ink-500 group-open:rotate-90 transition-transform"
                  aria-hidden>▸</span>
            <h3 className="label">Retrieved text</h3>
            <span className="font-mono text-[11px] text-ink-500">{decision.retrieved.length}</span>
            <span className="text-xs text-ink-500 ml-auto">show</span>
          </summary>
          <div className="px-4 pb-3 space-y-1.5">
            {decision.retrieved.map((chunk, i) => (
              <p key={i}
                 className="font-mono text-xs leading-relaxed text-ink-400
                            bg-ink-850 border border-ink-800 rounded px-2.5 py-2">
                {markMatches(chunk, refs).map((segment, j) =>
                  segment.hit
                    ? <mark key={j} className="bg-emerald-400/20 text-emerald-200 rounded px-0.5">{segment.text}</mark>
                    : <span key={j}>{segment.text}</span>
                )}
              </p>
            ))}
          </div>
        </details>
      )}

      {decision.advisories?.length > 0 && (
        <Section title="Advisories" count={decision.advisories.length}>
          <ul className="space-y-1">
            {decision.advisories.map((item, i) => (
              <li key={i} className="text-xs leading-snug text-sky-300/90 pl-3 border-l border-sky-900">
                {item}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {decision.warnings?.length > 0 && (
        <Section title="Not assessed" count={decision.warnings.length}>
          <ul className="space-y-1">
            {decision.warnings.map((item, i) => (
              <li key={i} className="text-xs leading-snug text-amber-300/90 pl-3 border-l border-amber-900">
                {item}
              </li>
            ))}
          </ul>
          <p className="text-xs text-ink-500 leading-snug pt-1">
            Each of these is shown rather than silently dropped, and most also cost confidence.
          </p>
        </Section>
      )}

      {decision.requires_human && decision.ticket_id && (
        <Section title="Human gate">
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-0.5 min-w-0">
              <div className="font-mono text-xs text-ink-200">{decision.ticket_id}</div>
              <div className="text-xs text-ink-500">
                {approvedBy
                  ? `Approved by ${approvedBy}. The verdict above stays as issued.`
                  : 'Open. The flight stays held until a person approves it.'}
              </div>
            </div>
            <button
              onClick={approve}
              disabled={!!approvedBy || approving}
              className="font-mono text-xs px-3 py-1.5 rounded border border-ink-700
                         text-ink-200 hover:bg-ink-800 disabled:opacity-50
                         disabled:cursor-not-allowed transition-colors whitespace-nowrap focus-ring">
              {approvedBy ? 'Approved' : approving ? 'Approving…' : 'Approve'}
            </button>
          </div>
          {approveError && (
            <p className="text-xs text-rose-300" role="alert">{approveError}</p>
          )}
          <p className="text-xs text-ink-500 leading-snug">
            Demo operator <span className="font-mono">ops@console</span>. A real deployment would require sign-in.
          </p>
        </Section>
      )}
    </div>
  )
}
