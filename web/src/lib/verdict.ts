import type { Verdict } from './api'

/**
 * Colour is reserved for verdict state. Nothing else in the interface is
 * saturated, so the decision is the only thing competing for attention.
 */
export const VERDICT_THEME: Record<Verdict, {
  label: string
  accent: string
  border: string
  bg: string
  dot: string
  meaning: string
}> = {
  ALLOW: {
    label: 'ALLOW',
    accent: 'text-emerald-300',
    border: 'border-emerald-900/70',
    bg: 'bg-emerald-950/40',
    dot: 'bg-emerald-400',
    meaning: 'Geometry is clear and every citation was found in the corpus.',
  },
  BLOCK: {
    label: 'BLOCK',
    accent: 'text-rose-300',
    border: 'border-rose-900/70',
    bg: 'bg-rose-950/40',
    dot: 'bg-rose-400',
    meaning: 'A ceiling or NOTAM restriction is breached.',
  },
  HOLD: {
    label: 'HOLD',
    accent: 'text-amber-300',
    border: 'border-amber-900/70',
    bg: 'bg-amber-950/40',
    dot: 'bg-amber-400',
    meaning: 'The decision could not be justified, so nothing was cleared.',
  },
  ERROR: {
    label: 'ERROR',
    accent: 'text-ink-400',
    border: 'border-ink-700',
    bg: 'bg-ink-850',
    dot: 'bg-ink-500',
    meaning: 'The request did not reach the API.',
  },
}

/**
 * The distinctive fragment of a reference, mirroring `core/citations.py::_needle`
 * so the UI highlights exactly what the backend matched on.
 */
export function needle(ref: string): string {
  const notam = ref.match(/NOTAM\s+(\d{2}\/\d{2})/i)
  if (notam) return notam[1]
  const car = ref.match(/§\s*(\d+)/)
  if (car) return `§${car[1]}`
  return ref
}

/** Split `text` into segments, marking the ones that match any needle. */
export function markMatches(text: string, refs: string[]): { text: string; hit: boolean }[] {
  const needles = refs.map(needle).filter(Boolean)
  if (needles.length === 0) return [{ text, hit: false }]

  const escaped = needles.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi')

  return text
    .split(pattern)
    .filter(segment => segment !== '')
    .map(segment => ({
      text: segment,
      hit: needles.some(n => segment.toLowerCase() === n.toLowerCase()),
    }))
}
