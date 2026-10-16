import type { FlightPlan } from './api'

/** The same limits the API enforces, so a bad plan is explained before it is sent. */
export type PlanErrors = Partial<Record<'lat' | 'lon' | 'alt' | 'drone_id' | 'query', string>>

export function validatePlan(plan: FlightPlan): PlanErrors {
  const errors: PlanErrors = {}
  if (!Number.isFinite(plan.lat) || plan.lat < -90 || plan.lat > 90) {
    errors.lat = 'Latitude must be a number from -90 to 90.'
  }
  if (!Number.isFinite(plan.lon) || plan.lon < -180 || plan.lon > 180) {
    errors.lon = 'Longitude must be a number from -180 to 180.'
  }
  if (!Number.isInteger(plan.alt) || plan.alt < 0 || plan.alt > 10000) {
    errors.alt = 'Altitude must be a whole number of metres, 0 to 10000.'
  }
  const droneId = plan.drone_id.trim()
  if (droneId.length < 1 || droneId.length > 64) {
    errors.drone_id = 'Drone id must be 1 to 64 characters.'
  }
  if (plan.query.length > 500) {
    errors.query = 'Keep the request under 500 characters.'
  }
  return errors
}

/** Identifies a plan, so the page can tell when the decision on screen is out of date. */
export function planKey(plan: FlightPlan): string {
  return JSON.stringify([plan.lat, plan.lon, plan.alt, plan.drone_id.trim(), plan.query])
}
