import { DEFAULT_QUERY, type FlightPlan } from './api'

export type Scenario = {
  id: string
  name: string
  /** What this case is meant to demonstrate, shown under the button row. */
  demonstrates: string
  expect: 'ALLOW' | 'BLOCK' | 'HOLD'
  plan: FlightPlan
}

/**
 * Four cases that cover every verdict the gate can return, so a visitor sees
 * the whole behaviour without knowing which coordinates matter.
 */
export const SCENARIOS: Scenario[] = [
  {
    id: 'breach',
    name: 'Crane breach',
    demonstrates:
      'Inside NOTAM 09/03 at 120m, above its 100m ceiling. Blocked, cited, and held for a human.',
    expect: 'BLOCK',
    plan: { lat: 18.53, lon: 73.84, alt: 120, drone_id: 'D12', query: DEFAULT_QUERY },
  },
  {
    id: 'clear',
    name: 'Clear flight',
    demonstrates:
      'Same position at 80m, under every ceiling. Cleared — but confidence is 0.85, not 1.0.',
    expect: 'ALLOW',
    plan: { lat: 18.53, lon: 73.84, alt: 80, drone_id: 'D12', query: DEFAULT_QUERY },
  },
  {
    id: 'advisory',
    name: 'Advisory zone',
    demonstrates:
      'Inside the bird-activity NOTAM, which states no limit. Reported to the operator, never auto-blocked.',
    expect: 'ALLOW',
    plan: { lat: 18.55, lon: 73.86, alt: 90, drone_id: 'D30', query: DEFAULT_QUERY },
  },
  {
    id: 'unchecked',
    name: 'Unchecked plan',
    demonstrates:
      'No regulatory question, so the router takes the act path and retrieves nothing. Geometry is clear — and it still holds.',
    expect: 'HOLD',
    plan: { lat: 18.52, lon: 73.85, alt: 100, drone_id: 'D40', query: 'D40 telemetry status check' },
  },
]
