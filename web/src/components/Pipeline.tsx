import { NODES, nodesRun } from '../lib/route'

/** The five steps a request passes through, with the ones this route skipped struck through. */
export function Pipeline({ action }: { action: string }) {
  const ran = nodesRun(action)

  return (
    <ol aria-label="Steps that ran for this request"
        className="flex flex-wrap items-center gap-x-1 gap-y-1.5">
      {NODES.map((node, i) => {
        const on = ran.has(node.id)
        return (
          <li key={node.id} className="flex items-center gap-1"
              title={on ? node.hint : `${node.label} was skipped on this route`}>
            {i > 0 && <span aria-hidden className="text-ink-500">›</span>}
            <span className={`font-mono text-[11px] px-1.5 py-0.5 rounded border
              ${on
                ? 'border-ink-700 bg-ink-850 text-ink-200'
                : 'border-ink-800 text-ink-500 line-through opacity-70'}`}>
              {node.label}
              {!on && <span className="sr-only"> (skipped)</span>}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
