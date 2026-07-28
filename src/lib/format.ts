import type { Signal, Stage, Decision } from './types'

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

// Browser Intl data for uz-Latn-UZ is unreliable (renders "2026 M07 26"),
// so month names are spelled out here instead of via toLocaleDateString.
const UZ_MONTHS_SHORT = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek']
const UZ_MONTHS_LONG = [
  'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
  'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
]

function formatUzDate(iso: string, months: string[]): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${d.getDate()}-${months[d.getMonth()]}, ${d.getFullYear()}`
}

export function formatDate(iso: string): string {
  return formatUzDate(iso, UZ_MONTHS_SHORT)
}

export function formatDateLong(iso: string): string {
  return formatUzDate(iso, UZ_MONTHS_LONG)
}

export const STAGE_LABEL: Record<Stage, string> = {
  'new': 'Yangi',
  'in-review': "Ko'rib chiqilmoqda",
  'recommended': 'Tavsiya etilgan',
  'advanced': "AQShga yo'llangan",
  'passed': 'Rad etilgan',
}

export const STAGE_ORDER: Stage[] = ['new', 'in-review', 'recommended', 'advanced', 'passed']

export const SIGNAL_LABEL: Record<Signal, string> = {
  high: 'Kuchli signal',
  medium: "O'rtacha signal",
  low: 'Past signal',
}

export const SIGNAL_ORDER: Record<Signal, number> = { high: 0, medium: 1, low: 2 }

export const DECISION_LABEL: Record<Decision, string> = {
  recommend: 'Tavsiya qilish',
  advance: "AQShga yo'llash",
  pass: 'Rad etish',
}

export const DECISION_STAGE: Record<Decision, Stage> = {
  recommend: 'recommended',
  advance: 'advanced',
  pass: 'passed',
}
