import { SCENARIOS, type Scenario } from '../lib/scenarios'
import { VERDICT_THEME } from '../lib/verdict'

/** Four ready-made flights. Each card says what it shows and what answer to expect. */
export function ScenarioCards({ activeId, onPick }: {
  activeId?: string
  onPick: (scenario: Scenario) => void
}) {
  return (
    <section aria-labelledby="examples-title" className="space-y-2">
      <h2 id="examples-title" className="text-sm font-medium text-ink-200">
        Try an example flight <span className="text-ink-500 font-normal">(one click, no typing)</span>
      </h2>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" role="group" aria-label="Example flights">
        {SCENARIOS.map(scenario => {
          const active = scenario.id === activeId
          const outcome = VERDICT_THEME[scenario.expect]
          return (
            <button
              key={scenario.id}
              onClick={() => onPick(scenario)}
              aria-pressed={active}
              className={`text-left rounded-lg border px-3.5 py-3 space-y-1.5 transition-colors focus-ring
                ${active
                  ? 'border-ink-400 bg-ink-850'
                  : 'border-ink-800 bg-ink-900 hover:border-ink-700 hover:bg-ink-850'}`}>
              <span className="block text-sm font-medium text-ink-200">{scenario.name}</span>
              <span className="block text-xs text-ink-400 leading-snug min-h-[2.75em]">{scenario.blurb}</span>
              <span className="flex items-center gap-1.5 text-xs text-ink-400">
                <span aria-hidden className={`w-2 h-2 rounded-full ${outcome.dot}`} />
                Expect: <span className={`font-medium ${outcome.accent}`}>{outcome.headline}</span>
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
