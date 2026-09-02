export type Evidence = { ref: string; grounded: boolean; excerpt: string }

export type Verdict = 'ALLOW' | 'BLOCK' | 'HOLD' | 'ERROR'

export type Decision = {
  verdict: Verdict
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

export type FlightPlan = {
  lat: number
  lon: number
  alt: number
  drone_id: string
  query: string
}

export const DEFAULT_QUERY = 'validate flight against DGCA CAR and active NOTAMs'

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`)
  return response.json() as Promise<T>
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  try {
    const res = await fetch(url, init)
    return await json<T>(res)
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error('Network error. Is the backend running?')
    }
    throw err
  }
}

export function validateFlight(plan: FlightPlan) {
  return request<Decision>('/api/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(plan),
  })
}

export function approveTicket(ticketId: string, approver: string) {
  return request<{ ticket_id: string; status: string }>(`/api/approve/${ticketId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approver }),
  })
}

export function listNotams() {
  return request<{ count: number; notams: Notam[] }>('/api/notams')
}

export function health() {
  return request<{ ok: boolean; version: string }>('/api/health')
}
