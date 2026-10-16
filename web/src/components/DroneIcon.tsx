const ROTORS: [number, number][] = [[7.5, 7.5], [24.5, 7.5], [7.5, 24.5], [24.5, 24.5]]

/**
 * A quadcopter seen from above. The rotor blades turn while `spinning`, which the
 * header uses to show that a check is in progress. The favicon is a separate static copy.
 */
export function DroneIcon({ className = '', spinning = false }: { className?: string; spinning?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" className={className} fill="none" aria-hidden="true" focusable="false">
      <path d="M10.5 10.5 21.5 21.5M21.5 10.5 10.5 21.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      {ROTORS.map(([x, y]) => (
        <g key={`${x}-${y}`}>
          <circle cx={x} cy={y} r="4.2" stroke="currentColor" strokeWidth="1.6" />
          <path className={spinning ? 'rotor-spin' : undefined} d={`M${x - 3} ${y}h6`}
                stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </g>
      ))}
      <rect x="11.5" y="11.5" width="9" height="9" rx="2.8" className="fill-sky-300" />
      <circle cx="16" cy="13.4" r="1" className="fill-ink-950" />
    </svg>
  )
}
