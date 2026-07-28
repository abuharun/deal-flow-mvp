import type { Signal, Stage, Decision } from './types'

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatDateLong(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
}

export const STAGE_LABEL: Record<Stage, string> = {
  'new': 'New',
  'in-review': 'In Review',
  'recommended': 'Recommended',
  'advanced': 'Advanced',
  'passed': 'Passed',
}

export const STAGE_ORDER: Stage[] = ['new', 'in-review', 'recommended', 'advanced', 'passed']

export const SIGNAL_LABEL: Record<Signal, string> = {
  high: 'High signal',
  medium: 'Medium signal',
  low: 'Low signal',
}

export const SIGNAL_ORDER: Record<Signal, number> = { high: 0, medium: 1, low: 2 }

export const DECISION_LABEL: Record<Decision, string> = {
  recommend: 'Recommend',
  advance: 'Advance to US',
  pass: 'Pass',
}

export const DECISION_STAGE: Record<Decision, Stage> = {
  recommend: 'recommended',
  advance: 'advanced',
  pass: 'passed',
}
