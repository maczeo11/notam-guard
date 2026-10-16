import { useState } from 'react'
import { approveTicket, type Decision } from '../lib/api'
import { routeCopy } from '../lib/route'
import { cleanReason, markMatches, VERDICT_THEME } from '../lib/verdict'
import { ConfidenceMeter } from './ConfidenceMeter'
import { Pipeline } from './Pipeline'

/** A labelled section that stays out of the way until it is opened. */
function Disclosure({ title, hint, count, defaultOpen = false, children }: {
  title: string
  hint?: string
  count?: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  return (
    <details className="border-t border-ink-800 group" open={defaultOpen}>
      <summary className="px-5 py-3 cursor-pointer list-none flex items-baseline gap-2 hover:bg-ink-850 focus-ring">
        <span className="font-mono text-[11px] text-ink-500 group-open:rotate-90 transition-transform" aria-hidden>▸</span>
        <h3 className="text-sm font-medium text-ink-200">{title}</h3>
        {count !== undefined && <span className="font-mono text-[11px] text-ink-500">{count}</span>}
        {hint && <span className="text-xs text-ink-500 ml-auto hidden sm:inline">{hint}</span>}
      </summary>
      <div className="px-5 pb-4 space-y-2">{children}</div>
    </details>
  )
}

export function EmptyState({ loading }: { loading: boolean }) {
  return (
    <div className="panel p-6 text-center space-y-2" aria-busy={loading}>
      <div className="text-sm font-medium text-ink-200">{loading ? 'Checking the flight…' : 'No answer yet'}</div>
      <p className="text-sm text-ink-400 leading-relaxed max-w-sm mx-auto">
        Pick an example flight, or move the pin and the height. The answer appears here.
      </p>
    </div>
  )
}

export function DecisionPanel({ decision, approvedBy, loading, updating, invalid, onApproved, onRecheck }: {
  decision: Decision
  approvedBy?: string
  loading: boolean
  /** The plan changed and a new check is on its way. */
  updating: boolean
  /** The plan has a field the gate cannot accept, so no new check can start. */
  invalid: boolean
  onApproved: (ticketId: string, approver: string) => void
  onRecheck: () => void
}) {
  const [approving, setApproving] = useState(false)
  const [approveError, setApproveError] = useState<string>()
  const theme = VERDICT_THEME[decision.verdict] ?? VERDICT_THEME.ERROR
  const refs = decision.citations ?? []
  const route = routeCopy(decision.action)
  const held = decision.verdict === 'HOLD'
  const outdated = (updating || invalid) && !loading

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
                     ${loading || outdated ? 'opacity-60' : ''}`}
         aria-busy={loading}>
      {outdated && (
        <div className="px-5 py-2 text-xs text-amber-300 bg-amber-950/40 border-b border-amber-900/60" role="status">
          {invalid
            ? 'Fix the highlighted field to check this flight. This answer is for the previous plan.'
            : 'Updating… this answer is for the previous plan.'}
        </div>
      )}
      {loading && (
        <div className="px-5 py-2 text-xs text-ink-400 bg-ink-850 border-b border-ink-800" role="status">
          Checking the flight…
        </div>
      )}

      {/* The answer. The only saturated element on the page. */}
      <div className={`px-5 py-5 space-y-3 ${theme.bg}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0" role="status" aria-live="polite">
            <span aria-hidden
                  className={`shrink-0 w-10 h-10 rounded-full border flex items-center justify-center
                              font-mono text-lg font-semibold ${theme.accent} ${theme.border}`}>
              {theme.glyph}
            </span>
            <div className="min-w-0">
              <div className={`text-2xl sm:text-3xl font-semibold tracking-tight leading-tight ${theme.accent}`}>
                {theme.headline}
              </div>
              <div className="label mt-0.5">Gate: {theme.label}</div>
            </div>
          </div>
          <button onClick={onRecheck} disabled={loading}
                  className="shrink-0 font-mono text-[11px] px-2.5 py-1.5 rounded border border-ink-700
                             text-ink-400 hover:text-ink-200 hover:bg-ink-800 disabled:opacity-50
                             transition-colors focus-ring">
            Check again
          </button>
        </div>

        <p className="text-sm text-ink-200 leading-relaxed">{theme.plain}</p>

        <div className="rounded border border-ink-800 bg-ink-950/40 px-3 py-2">
          <div className="label">The gate's note</div>
          <p className="text-sm text-ink-200 leading-relaxed mt-0.5">{cleanReason(decision.reason, decision.verdict)}</p>
        </div>

        {typeof decision.confidence === 'number' && (
          <ConfidenceMeter value={decision.confidence} verdict={decision.verdict} tone={theme.accent} />
        )}
      </div>

      {decision.requires_human && (
        <div className="border-t border-ink-800 px-5 py-4 space-y-2">
          {decision.ticket_id ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 space-y-0.5">
                  <div className="text-sm font-medium text-ink-200">A person has to approve this flight</div>
                  <div className="text-xs text-ink-400 leading-snug">
                    {approvedBy
                      ? `Approved by ${approvedBy}. The answer above stays as the gate issued it.`
                      : <>Ticket <span className="font-mono text-ink-200">{decision.ticket_id}</span> is open. The flight stays held until someone approves it.</>}
                  </div>
                </div>
                <button
                  onClick={approve}
                  disabled={!!approvedBy || approving}
                  className="shrink-0 font-mono text-xs px-3 py-1.5 rounded border border-ink-700
                             text-ink-200 hover:bg-ink-800 disabled:opacity-50
                             disabled:cursor-not-allowed transition-colors whitespace-nowrap focus-ring">
                  {approvedBy ? 'Approved' : approving ? 'Approving…' : 'Approve'}
                </button>
              </div>
              {approveError && <p className="text-xs text-rose-300" role="alert">{approveError}</p>}
              <p className="text-xs text-ink-500 leading-snug">
                Demo only: approvals are recorded as <span className="font-mono">ops@console</span>.
                A real deployment would require sign-in.
              </p>
            </>
          ) : (
            <p className="text-xs text-ink-400 leading-snug">
              A person has to review this flight, but no approval ticket could be opened right now.
              The flight stays held.
            </p>
          )}
        </div>
      )}

      {decision.evidence?.length > 0 && (
        <Disclosure title="Rules it relied on" hint="the official text behind the answer"
                    count={decision.evidence.length} defaultOpen={!held}>
          {decision.evidence.map(item => (
            <div key={item.ref} className="bg-ink-850 border border-ink-800 rounded px-2.5 py-2 space-y-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className={`font-mono text-xs ${item.grounded ? 'text-emerald-300' : 'text-rose-300'}`} aria-hidden>
                  {item.grounded ? '✓' : '✗'}
                </span>
                <span className="font-mono text-xs text-ink-200 whitespace-nowrap">{item.ref}</span>
                <span className="label sm:ml-auto">
                  {item.grounded ? 'found in the official text' : 'not found in the official text'}
                </span>
              </div>
              {item.excerpt && <p className="text-xs leading-snug text-ink-400 pl-5">{item.excerpt}</p>}
            </div>
          ))}
        </Disclosure>
      )}

      {decision.warnings?.length > 0 && (
        <Disclosure title="What it could not check" hint="each one is shown, not hidden"
                    count={decision.warnings.length} defaultOpen={held}>
          <ul className="space-y-1">
            {decision.warnings.map((item, i) => (
              <li key={i} className="text-xs leading-snug text-amber-300/90 pl-3 border-l border-amber-900">{item}</li>
            ))}
          </ul>
          <p className="text-xs text-ink-500 leading-snug pt-1">
            Each of these is shown rather than silently dropped, and most also lower how sure the gate is.
          </p>
        </Disclosure>
      )}

      {decision.advisories?.length > 0 && (
        <Disclosure title="Nearby notices" hint="caution only, nothing blocked" count={decision.advisories.length}>
          <ul className="space-y-1">
            {decision.advisories.map((item, i) => (
              <li key={i} className="text-xs leading-snug text-sky-300/90 pl-3 border-l border-sky-900">{item}</li>
            ))}
          </ul>
        </Disclosure>
      )}

      <Disclosure title="How it was checked" hint={route.name}>
        <Pipeline action={decision.action} />
        {route.detail && <p className="text-xs text-ink-400 leading-snug">{route.detail}</p>}
        <p className="text-xs text-ink-500 leading-snug">
          Steps with a line through them did not run for this request. Hover a step to see what it does.
        </p>
      </Disclosure>

      {decision.retrieved?.length > 0 && (
        <Disclosure title="Source text it read" hint="the rules and notices it looked up"
                    count={decision.retrieved.length}>
          {decision.retrieved.map((chunk, i) => (
            <p key={i} className="font-mono text-xs leading-relaxed text-ink-400
                                  bg-ink-850 border border-ink-800 rounded px-2.5 py-2">
              {markMatches(chunk, refs).map((segment, j) =>
                segment.hit
                  ? <mark key={j} className="bg-emerald-400/20 text-emerald-200 rounded px-0.5">{segment.text}</mark>
                  : <span key={j}>{segment.text}</span>
              )}
            </p>
          ))}
        </Disclosure>
      )}
    </div>
  )
}
