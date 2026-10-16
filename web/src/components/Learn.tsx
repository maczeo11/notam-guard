import { VERDICT_THEME } from '../lib/verdict'

const ANSWERS = (['ALLOW', 'BLOCK', 'HOLD'] as const).map(key => VERDICT_THEME[key])

const WORDS: [string, string][] = [
  ['NOTAM', 'A short official notice about a temporary airspace restriction, such as a crane or a closed runway.'],
  ['Above ground', 'Height measured from the ground below the drone, not from sea level.'],
  ['Rule it relied on', 'The clause or notice the answer cites, with its official text shown so you can check it.'],
  ['How sure it is', 'A number from 0 to 1. It drops for every restriction the gate could not check.'],
]

/** Plain explanations for anyone who wants to know why the answer says what it says. */
export function Learn() {
  return (
    <section aria-labelledby="learn-title" className="space-y-3">
      <h2 id="learn-title" className="text-sm font-medium text-ink-200">How it decides</h2>
      <div className="grid gap-3 lg:grid-cols-3">
        <div className="panel p-4 space-y-2.5">
          <h3 className="label">The three answers</h3>
          <ul className="space-y-2">
            {ANSWERS.map(answer => (
              <li key={answer.label} className="flex gap-2.5">
                <span aria-hidden className={`mt-1.5 shrink-0 w-2 h-2 rounded-full ${answer.dot}`} />
                <span className="text-xs text-ink-400 leading-snug">
                  <span className={`block text-sm font-medium ${answer.accent}`}>{answer.headline}</span>
                  {answer.plain}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel p-4 space-y-2.5">
          <h3 className="label">Words you will see</h3>
          <dl className="space-y-2">
            {WORDS.map(([term, meaning]) => (
              <div key={term}>
                <dt className="text-sm font-medium text-ink-200">{term}</dt>
                <dd className="text-xs text-ink-400 leading-snug">{meaning}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="panel p-4 space-y-2.5">
          <h3 className="label">What is real here</h3>
          <p className="text-xs text-ink-400 leading-relaxed">
            This is a prototype on sample data: four clauses from the DGCA drone rules and three
            example notices. It is not for planning real flights.
          </p>
          <p className="text-xs text-ink-400 leading-relaxed">
            The answer comes from plain code, never from a language model, so the same plan always
            gets the same answer. A model can optionally pick which checks to run and word one
            sentence; this demo runs without one.
          </p>
          <p className="text-xs text-ink-400 leading-relaxed">
            When the gate cannot check something, it holds the flight instead of guessing.
          </p>
        </div>
      </div>
    </section>
  )
}
