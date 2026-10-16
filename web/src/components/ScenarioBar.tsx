import { SCENARIOS, type Scenario } from '../lib/scenarios'

export function ScenarioBar({ activeId, onPick }: {
  activeId?: string
  onPick: (scenario: Scenario) => void
}) {
  const active = SCENARIOS.find(s => s.id === activeId)

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Example flight plans">
        <span className="label mr-1">Try a case</span>
        {SCENARIOS.map(scenario => {
          const isActive = scenario.id === activeId
          return (
            <button
              key={scenario.id}
              onClick={() => onPick(scenario)}
              aria-pressed={isActive}
              className={`font-mono text-xs px-2.5 py-1.5 rounded border transition-colors focus-ring
                ${isActive
                  ? 'bg-ink-800 border-ink-700 text-ink-200'
                  : 'bg-ink-900 border-ink-800 text-ink-400 hover:text-ink-200 hover:border-ink-700'}`}>
              {scenario.name}
            </button>
          )
        })}
      </div>
      <p className="text-xs leading-snug text-ink-500 min-h-[2.4em]" aria-live="polite">
        {active
          ? active.demonstrates
          : 'Custom plan. Edit the fields or tap the map, then press “Validate plan”.'}
      </p>
    </div>
  )
}
