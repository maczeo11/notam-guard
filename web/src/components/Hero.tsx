const STEPS = [
  { title: 'Pick a flight', body: 'Choose an example below, or drag the pin on the map.' },
  { title: 'The gate checks it', body: 'It tests the height and the place against the drone rules and any temporary limits.' },
  { title: 'You get a clear answer', body: 'Fly, do not fly, or a person must decide, with the rule it relied on.' },
]

/** What this is, in words anyone can follow, before any control appears. */
export function Hero() {
  return (
    <section aria-labelledby="hero-title" className="space-y-5">
      <div className="max-w-3xl space-y-3">
        <p className="label !text-sky-300">A pre-flight safety check for drones</p>
        <h1 id="hero-title" className="text-3xl sm:text-4xl font-semibold tracking-tight text-ink-200 leading-tight text-balance">
          Is this drone flight allowed? Get a straight answer.
        </h1>
        <p className="text-base text-ink-400 leading-relaxed">
          Some places have temporary flying limits, such as a crane that caps flights at 100 m.
          NOTAM-Guard checks a planned flight against those limits and the national drone rules,
          then tells you to <strong className="text-ink-200 font-medium">fly</strong>,{' '}
          <strong className="text-ink-200 font-medium">not fly</strong>, or{' '}
          <strong className="text-ink-200 font-medium">ask a person</strong>.
          It always shows the rule it relied on.
        </p>
      </div>

      <ol className="grid gap-2 sm:grid-cols-3" aria-label="How it works">
        {STEPS.map((step, i) => (
          <li key={step.title} className="flex gap-3 rounded-lg border border-ink-800 bg-ink-900/60 px-3.5 py-3">
            <span aria-hidden
                  className="shrink-0 w-6 h-6 rounded-full border border-ink-700 font-mono text-xs
                             text-sky-300 flex items-center justify-center">{i + 1}</span>
            <span>
              <span className="block text-sm font-medium text-ink-200">{step.title}</span>
              <span className="block text-xs text-ink-400 leading-snug mt-0.5">{step.body}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
