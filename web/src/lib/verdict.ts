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

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * Where `ref` is *defined* in `chunk`, mirroring `find_definition` in
 * `core/citations.py` so the UI marks exactly what the backend grounded on.
 *
 * A reference counts only at the start of the chunk or of a sentence, and as a
 * whole number: "§7 Micro RPA" defines §7, "DGCA CAR §7 applies" only mentions it,
 * and "§70" is not §7. Returns null when the chunk does not define the reference.
 */
export function findDefinition(chunk: string, ref: string): { start: number; end: number } | null {
  const notam = ref.match(/NOTAM\s+(\d{2}\/\d{2})/i)
  const car = ref.match(/§\s*(\d+)/)

  let pattern: RegExp
  if (notam) {
    pattern = new RegExp(`(?:^|[.;:]\\s)\\W*(NOTAM\\s+${escapeRegExp(notam[1])})(?![\\d/])`, 'i')
  } else if (car) {
    pattern = new RegExp(`(?:^|[.;:]\\s)\\W*(§\\s*${car[1]})(?!\\d)`)
  } else {
    pattern = new RegExp(`(${escapeRegExp(ref)})`, 'i')
  }

  const match = pattern.exec(chunk)
  if (!match) return null
  const start = match.index + match[0].length - match[1].length
  return { start, end: start + match[1].length }
}

/** Split `text` into segments, marking each reference where the text defines it. */
export function markMatches(text: string, refs: string[]): { text: string; hit: boolean }[] {
  const spans = refs
    .map(ref => findDefinition(text, ref))
    .filter((span): span is { start: number; end: number } => span !== null)
    .sort((a, b) => a.start - b.start)

  const segments: { text: string; hit: boolean }[] = []
  let cursor = 0
  for (const span of spans) {
    if (span.start < cursor) continue            // overlaps one already marked
    if (span.start > cursor) segments.push({ text: text.slice(cursor, span.start), hit: false })
    segments.push({ text: text.slice(span.start, span.end), hit: true })
    cursor = span.end
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), hit: false })
  return segments.length > 0 ? segments : [{ text, hit: false }]
}
