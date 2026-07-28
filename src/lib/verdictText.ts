import type { Lang, Startup } from './types'
import { composeVerdict } from './compose'
import { VC_NAME } from './seed'
import { formatDateLong } from './format'

/**
 * Resolve the verdict text for a requested language. The stored English and
 * founder-language versions are canonical (English may carry VC edits); any
 * third language is rendered on the fly from the same notes, deterministically.
 */
export function verdictTextFor(startup: Startup, lang: Lang): string {
  const v = startup.verdict
  if (!v) return ''
  if (lang === 'en') return v.en
  if (lang === v.localLang) return v.local
  return composeVerdict({
    decision: v.decision,
    notes: startup.notes,
    startupName: startup.name,
    founderName: startup.founder.name,
    vcName: VC_NAME,
    lang,
    dateLabel: formatDateLong(v.sentAt ?? v.composedAt, lang),
  })
}
