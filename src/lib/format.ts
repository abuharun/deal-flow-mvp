import type { Decision, Lang, Stage } from './types'

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

// Browser Intl data for uz-Latn-UZ is unreliable (renders "2026 M07 26"), and
// tests must not depend on the host's ICU build or timezone — so month names
// for every supported language are spelled out and UTC dates are assembled by hand.
const MONTHS: Record<Lang, { short: string[]; long: string[] }> = {
  uz: {
    short: ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek'],
    long: [
      'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
      'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr',
    ],
  },
  ru: {
    short: ['янв.', 'февр.', 'мар.', 'апр.', 'мая', 'июн.', 'июл.', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.'],
    long: [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
    ],
  },
  en: {
    short: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    long: [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ],
  },
}

function assemble(iso: string, lang: Lang, months: string[]): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const day = d.getUTCDate()
  const month = months[d.getUTCMonth()]
  const year = d.getUTCFullYear()
  // Uzbek keeps its established "26-iyl, 2026" shape; Russian and English
  // read naturally as "26 июл. 2026" / "26 Jul 2026".
  return lang === 'uz' ? `${day}-${month}, ${year}` : `${day} ${month} ${year}`
}

export function formatDate(iso: string, lang: Lang = 'uz'): string {
  return assemble(iso, lang, MONTHS[lang].short)
}

export function formatDateLong(iso: string, lang: Lang = 'uz'): string {
  return assemble(iso, lang, MONTHS[lang].long)
}

export const STAGE_ORDER: Stage[] = ['new', 'in-review', 'recommended', 'advanced', 'passed']

export const SIGNAL_ORDER: Record<'high' | 'medium' | 'low', number> = { high: 0, medium: 1, low: 2 }

export const DECISION_STAGE: Record<Decision, Stage> = {
  recommend: 'recommended',
  advance: 'advanced',
  pass: 'passed',
}
