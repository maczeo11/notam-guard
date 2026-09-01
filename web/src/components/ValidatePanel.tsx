import { useState } from 'react'
import { approveTicket, validateFlight, type Decision } from '../lib/api'

const VERDICT_STYLES: Record<string, string> = {
  ALLOW: 'bg-emerald-950 border-emerald-800 text-emerald-200',
  BLOCK: 'bg-rose-950 border-rose-800 text-rose-200',
  HOLD: 'bg-amber-950 border-amber-800 text-amber-200',
  ERROR: 'bg-slate-800 border-slate-700 text-slate-300',
}

export function ValidatePanel({ lat, lon, onVerdict }: {
  lat: number
  lon: number
  onVerdict?: (verdict: string) => void
}) {
  const [alt, setAlt] = useState(120)
  const [drone, setDrone] = useState('D12')
  const [decision, setDecision] = useState<Decision | null>(null)
  const [loading, setLoading] = useState(false)
  const [approved, setApproved] = useState(false)

  async function run() {
    setLoading(true)
    setApproved(false)
    try {
      const result = await validateFlight(lat, lon, alt, drone)
      setDecision(result)
      onVerdict?.(result.verdict)
    } catch (error) {
      setDecision({ verdict: 'ERROR', reason: String(error) } as Decision)
    } finally {
      setLoading(false)
    }
  }

  async function approve() {
    if (!decision?.ticket_id) return
    await approveTicket(decision.ticket_id, 'ops@console')
    setApproved(true)
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <input value={lat.toFixed(4)} readOnly aria-label="latitude"
               className="bg-slate-800 rounded px-2 py-1 text-sm text-slate-400" />
        <input value={lon.toFixed(4)} readOnly aria-label="longitude"
               className="bg-slate-800 rounded px-2 py-1 text-sm text-slate-400" />
        <input type="number" value={alt} aria-label="altitude AGL in metres"
               onChange={e => setAlt(parseInt(e.target.value) || 0)}
               className="bg-slate-800 rounded px-2 py-1 text-sm" />
      </div>
      <input value={drone} onChange={e => setDrone(e.target.value)} aria-label="drone id"
             className="w-full bg-slate-800 rounded px-2 py-1 text-sm" placeholder="drone_id" />
      <button onClick={run} disabled={loading}
              className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded py-2 text-sm font-medium">
        {loading ? 'Checking…' : 'Validate flight plan'}
      </button>

      {decision && (
        <div className={`rounded p-3 text-sm border ${VERDICT_STYLES[decision.verdict]}`}>
          <div className="flex items-baseline justify-between">
            <span className="font-bold">{decision.verdict}</span>
            {decision.confidence !== undefined && (
              <span className="text-xs opacity-70">
                confidence {decision.confidence} · route {decision.action}
              </span>
            )}
          </div>
          <div className="text-xs opacity-90 mt-1">{decision.reason}</div>

          {decision.evidence?.length > 0 && (
            <div className="mt-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wider opacity-60">Evidence</div>
              {decision.evidence.map(item => (
                <div key={item.ref} className="text-xs bg-slate-900/60 border border-slate-700 rounded px-2 py-1">
                  <span className={item.grounded ? 'text-emerald-300' : 'text-rose-300'}>
                    {item.grounded ? '✓' : '✗'} {item.ref}
                  </span>
                  {item.excerpt && <div className="opacity-60 mt-0.5">{item.excerpt}</div>}
                </div>
              ))}
            </div>
          )}

          {decision.advisories?.length > 0 && (
            <ul className="mt-2 text-xs opacity-80 list-disc list-inside">
              {decision.advisories.map(a => <li key={a}>{a}</li>)}
            </ul>
          )}

          {decision.warnings?.length > 0 && (
            <div className="mt-2 text-xs border-l-2 border-amber-600 pl-2 opacity-80">
              <div className="uppercase tracking-wider text-[11px] opacity-70">Not assessed</div>
              <ul className="list-disc list-inside">
                {decision.warnings.map(w => <li key={w}>{w}</li>)}
              </ul>
            </div>
          )}

          {decision.requires_human && decision.ticket_id && (
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-xs">Held · ticket {decision.ticket_id}</span>
              <button onClick={approve} disabled={approved}
                      className="text-xs bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded px-2 py-1">
                {approved ? 'Approved' : 'Approve as operator'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
