import { useState } from 'react'
import { approveTicket, type Decision } from '../lib/api'
import { markMatches, VERDICT_THEME } from '../lib/verdict'
import { ConfidenceMeter } from './ConfidenceMeter'

function Section({ title, count, children }: {
  title: string
  count?: number
  children: React.ReactNode
}) {
  return (
    <section className="border-t border-ink-800 px-4 py-3 space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="label">{title}</h3>
        {count !== undefined && <span className="font-mono text-[10px] text-ink-700">{count}</span>}
      </div>
      {children}
    </section>
  )
}

export function EmptyState() {
  return (
    <div className="panel p-6 text-center space-y-2">
      <div className="font-mono text-xs uppercase tracking-[0.14em] text-ink-500">
        No decision yet
      </div>
      <p className="text-sm text-ink-400 leading-relaxed max-w-sm mx-auto">
        Submit a flight plan and the gate returns <span className="text-emerald-300">ALLOW</span>,{' '}
        <span className="text-rose-300">BLOCK</span> or <span className="text-amber-300">HOLD</span> —
        with the regulation it relied on and the retrieved text that supports it.
      </p>
    </div>
  )
}

export function DecisionPanel({ decision }: { decision: Decision }) {
  const [approved, setApproved] = useState(false)
  const [approving, setApproving] = useState(false)
  const theme = VERDICT_THEME[decision.verdict] ?? VERDICT_THEME.ERROR
  const refs = decision.citations ?? []

  async function approve() {
    if (!decision.ticket_id) return
    setApproving(true)
    try {
      await approveTicket(decision.ticket_id, 'ops@console')
      setApproved(true)
    } finally {
      setApproving(false)
    }
  }

  return (
    <div className={`panel overflow-hidden animate-rise ${theme.border}`}>
      {/* Verdict — the only saturated element on the page. */}
      <div className={`px-4 py-4 space-y-3 ${theme.bg}`}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className={`w-2 h-2 rounded-full ${theme.dot}`} />
            <span className={`font-mono text-2xl font-semibold tracking-tight ${theme.accent}`}>
              {theme.label}
            </span>
          </div>
          <div className="text-right">
            <div className="label">route</div>
            <div className="font-mono text-xs text-ink-400">{decision.action || '—'}</div>
          </div>
        </div>

        <p className="text-[11px] text-ink-500 leading-snug">{theme.meaning}</p>
        <p className="text-sm text-ink-200 leading-relaxed">{decision.reason}</p>

        {typeof decision.confidence === 'number' && (
          <div className="pt-1">
            <ConfidenceMeter value={decision.confidence} tone={theme.accent} />
          </div>
        )}
      </div>

      {decision.evidence?.length > 0 && (
        <Section title="Evidence" count={decision.evidence.length}>
          <div className="space-y-1.5">
            {decision.evidence.map(item => (
              <div key={item.ref}
                   className="bg-ink-850 border border-ink-800 rounded px-2.5 py-2 space-y-1">
                <div className="flex items-center gap-2">
                  <span className={`font-mono text-xs ${item.grounded ? 'text-emerald-300' : 'text-rose-300'}`}>
                    {item.grounded ? '✓' : '✗'}
                  </span>
                  <span className="font-mono text-xs text-ink-200">{item.ref}</span>
                  <span className="label ml-auto">
                    {item.grounded ? 'found in corpus' : 'not retrieved'}
                  </span>
                </div>
                {item.excerpt && (
                  <p className="text-[11px] leading-snug text-ink-500 pl-5">{item.excerpt}</p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {decision.retrieved?.length > 0 && (
        <Section title="Retrieved chunks" count={decision.retrieved.length}>
          <div className="space-y-1.5">
            {decision.retrieved.map((chunk, i) => (
              <p key={i}
                 className="font-mono text-[11px] leading-relaxed text-ink-400
                            bg-ink-850 border border-ink-800 rounded px-2.5 py-2">
                {markMatches(chunk, refs).map((segment, j) =>
                  segment.hit
                    ? <mark key={j} className="bg-emerald-400/20 text-emerald-200 rounded px-0.5">{segment.text}</mark>
                    : <span key={j}>{segment.text}</span>
                )}
              </p>
            ))}
          </div>
        </Section>
      )}

      {decision.advisories?.length > 0 && (
        <Section title="Advisories" count={decision.advisories.length}>
          <ul className="space-y-1">
            {decision.advisories.map(item => (
              <li key={item} className="text-[11px] leading-snug text-sky-300/80 pl-3 border-l border-sky-900">
                {item}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {decision.warnings?.length > 0 && (
        <Section title="Not assessed" count={decision.warnings.length}>
          <ul className="space-y-1">
            {decision.warnings.map(item => (
              <li key={item} className="text-[11px] leading-snug text-amber-300/80 pl-3 border-l border-amber-900">
                {item}
              </li>
            ))}
          </ul>
          <p className="text-[10px] text-ink-700 leading-snug pt-1">
            Each of these costs confidence rather than being silently dropped.
          </p>
        </Section>
      )}

      {decision.requires_human && decision.ticket_id && (
        <Section title="Human gate">
          <div className="flex items-center justify-between gap-3">
            <div className="space-y-0.5">
              <div className="font-mono text-xs text-ink-200">{decision.ticket_id}</div>
              <div className="text-[10px] text-ink-500">
                {approved ? 'Approved by ops@console' : 'Open — the flight is held until approved'}
              </div>
            </div>
            <button
              onClick={approve}
              disabled={approved || approving}
              className="font-mono text-[11px] px-3 py-1.5 rounded border border-ink-700
                         text-ink-200 hover:bg-ink-800 disabled:opacity-40
                         disabled:cursor-not-allowed transition-colors whitespace-nowrap">
              {approved ? 'Approved' : approving ? 'Approving…' : 'Approve'}
            </button>
          </div>
        </Section>
      )}
    </div>
  )
}
