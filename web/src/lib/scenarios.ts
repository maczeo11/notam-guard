import { DEFAULT_QUERY, type FlightPlan } from './api'

export type Scenario = {
  id: string
  /** Plain words, written for someone who has never heard of a NOTAM. */
  name: string
  /** What happens in this example, in one or two short sentences. */
  blurb: string
  expect: 'ALLOW' | 'BLOCK' | 'HOLD'
  plan: FlightPlan
}

/**
 * Four examples that cover every answer the gate can give, so a visitor sees the
 * whole behaviour without knowing which coordinates matter.
 */
export const SCENARIOS: Scenario[] = [
  {
    id: 'breach',
    name: 'Too high near a crane',
    blurb: 'A crane notice caps flights here at 100 m. This plan flies at 120 m.',
    expect: 'BLOCK',
    plan: { lat: 18.53, lon: 73.84, alt: 120, drone_id: 'D12', query: DEFAULT_QUERY },
  },
  {
    id: 'clear',
    name: 'A clear flight',
    blurb: 'The same spot at 80 m, under every limit.',
    expect: 'ALLOW',
    plan: { lat: 18.53, lon: 73.84, alt: 80, drone_id: 'D12', query: DEFAULT_QUERY },
  },
  {
    id: 'advisory',
    name: 'Birds nearby',
    blurb: 'A bird-activity notice with no height limit. It is reported, not blocked.',
    expect: 'ALLOW',
    plan: { lat: 18.55, lon: 73.86, alt: 90, drone_id: 'D30', query: DEFAULT_QUERY },
  },
  {
    id: 'unchecked',
    name: 'Not enough to go on',
    blurb: 'The request names no rule, so nothing backs up an answer. The flight is held.',
    expect: 'HOLD',
    plan: { lat: 18.52, lon: 73.85, alt: 100, drone_id: 'D40', query: 'D40 telemetry status check' },
  },
]
