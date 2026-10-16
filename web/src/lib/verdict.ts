import type { Verdict } from './api'

/**
 * Colour is reserved for verdict state. Nothing else in the interface is
 * saturated, so the decision is the only thing competing for attention.
 *
 * `headline` is what a first-time visitor reads; `label` is the gate's own word
 * (the API, the docs and the CV all say ALLOW, BLOCK and HOLD), shown beside it.
 */
export const VERDICT_THEME: Record<Verdict, {
  label: string
  headline: string
  glyph: string
  accent: string
  border: string
  bg: string
  dot: string
  plain: string
}> = {
  ALLOW: {
    label: 'ALLOW',
    headline: 'Clear to fly',
    glyph: '✓',
    accent: 'text-emerald-300',
    border: 'border-emerald-900/70',
    bg: 'bg-emerald-950/40',
    dot: 'bg-emerald-400',
    plain: 'No rule or restriction is broken, and the official text backs that up.',
  },
  BLOCK: {
    label: 'BLOCK',
    headline: 'Do not fly',
    glyph: '✕',
    accent: 'text-rose-300',
    border: 'border-rose-900/70',
    bg: 'bg-rose-950/40',
    dot: 'bg-rose-400',
    plain: 'This plan breaks a rule or a restriction. A person has to review it.',
  },
  HOLD: {
    label: 'HOLD',
    headline: 'Held for a person',
    glyph: '!',
    accent: 'text-amber-300',
    border: 'border-amber-900/70',
    bg: 'bg-amber-950/40',
    dot: 'bg-amber-400',
    plain: 'The gate could not fully check this plan, so it will not clear it. A person has to decide.',
  },
  ERROR: {
    label: 'ERROR',
    headline: 'Could not check',
    glyph: '?',
    accent: 'text-ink-400',
    border: 'border-ink-700',
    bg: 'bg-ink-850',
    dot: 'bg-ink-500',
    plain: 'The request did not reach the gate.',
  },
}

/**
 * The gate's own sentence, without the verdict word it starts with (the headline
 * already says it, and a "clear:" under "Held for a person" reads as a contradiction)
 * and with the abbreviation spelled out.
 */
export function cleanReason(reason: string, verdict: Verdict): string {
  return reason
    .replace(new RegExp(`^${verdict}:\\s*`), '')
    .replace(/^clear:\s*/i, '')
    .replace(/\bAGL\b/g, 'above ground')
    .trim()
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
