import { SCENARIOS, type Scenario } from '../lib/scenarios'

export function ScenarioBar({ activeId, onPick }: {
  activeId?: string
  onPick: (scenario: Scenario) => void
}) {
  const active = SCENARIOS.find(s => s.id === activeId)

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {SCENARIOS.map(scenario => {
          const isActive = scenario.id === activeId
          return (
            <button
              key={scenario.id}
              onClick={() => onPick(scenario)}
              className={`font-mono text-xs px-2.5 py-1.5 rounded border transition-colors
                ${isActive
                  ? 'bg-ink-800 border-ink-700 text-ink-200'
                  : 'bg-ink-900 border-ink-800 text-ink-400 hover:text-ink-200 hover:border-ink-700'}`}>
              {scenario.name}
            </button>
          )
        })}
      </div>
      <p className="text-[11px] leading-snug text-ink-500 min-h-[2.2em]">
        {active
          ? active.demonstrates
          : 'Pick a case to run it, or click the map and enter a plan of your own.'}
      </p>
    </div>
  )
}
