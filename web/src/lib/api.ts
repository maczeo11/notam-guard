export type Evidence = { ref: string; grounded: boolean; excerpt: string }

export type Decision = {
  verdict: 'ALLOW' | 'BLOCK' | 'HOLD' | 'ERROR'
  reason: string
  confidence: number
  citations: string[]
  evidence: Evidence[]
  advisories: string[]
  warnings: string[]
  requires_human: boolean
  ticket_id: string
  retrieved: string[]
  action: string
}

export type Notam = {
  id: string
  severity: string
  geolocatable: boolean
  lat: number | null
  lon: number | null
  radius_km: number | null
  max_alt_m: number | null
  valid_from: string | null
  valid_to: string | null
  source: string
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`)
  return response.json() as Promise<T>
}

export function validateFlight(lat: number, lon: number, alt: number, drone_id: string) {
  return fetch('/api/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lat, lon, alt, drone_id,
      query: 'validate flight against DGCA CAR and active NOTAMs',
    }),
  }).then(json<Decision>)
}

export function approveTicket(ticketId: string, approver: string) {
  return fetch(`/api/approve/${ticketId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approver }),
  }).then(json<{ ticket_id: string; status: string }>)
}

export function listNotams() {
  return fetch('/api/notams').then(json<{ count: number; notams: Notam[] }>)
}

export function health() {
  return fetch('/api/health').then(json<{ ok: boolean; version: string }>)
}
