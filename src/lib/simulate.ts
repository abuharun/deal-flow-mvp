import type { Recommendation, Signal, StepKey, SubmissionDraft } from './types'
import { STEP_KEYS } from './types'

/**
 * Simulated AI for the demo. Deterministic on purpose: the same submission
 * always yields the same summary and recommendation, so the demo is
 * reproducible. Production swaps this for a real model behind the same shape.
 */

/** Take the first ~2 sentences of a raw field, capped for card display. */
export function summarizeField(raw: string, cap = 260): string {
  const text = raw.trim().replace(/\s+/g, ' ')
  if (!text) return "Asoschi tomonidan to'ldirilmagan."
  const sentences = text.split(/(?<=[.!?])\s+/)
  let out = sentences.slice(0, 2).join(' ')
  if (out.length > cap) out = out.slice(0, cap - 1).trimEnd() + '…'
  return out
}

export function summarizeDraft(draft: SubmissionDraft): Record<StepKey, string> {
  const summary = {} as Record<StepKey, string>
  for (const key of STEP_KEYS) summary[key] = summarizeField(draft.fields[key])
  return summary
}

// Uzbek and English keywords both count — founders paste from either language.
const POSITIVE = [
  /paying/i,
  /revenue/i,
  /customers?/i,
  /grow(th|ing)/i,
  /contract/i,
  /retention/i,
  /profit/i,
  /daromad/i,
  /mijoz/i,
  /o['ʻ’]s(ish|moqda|ib)/i,
  /shartnoma/i,
  /foyda/i,
  /to['ʻ’]lovchi/i,
]
const NEGATIVE = [
  /no revenue/i,
  /pre-?revenue/i,
  /idea stage/i,
  /not launched/i,
  /no users/i,
  /prototype only/i,
  /daromad(imiz)? yo['ʻ’]q/i,
  /hali daromad/i,
  /daromadsiz/i,
  /g['ʻ’]oya bosqichi/i,
  /ishga tushmagan/i,
  /foydalanuvchi yo['ʻ’]q/i,
  /faqat prototip/i,
]

/** Rule-based readiness read. Ranks attention; it is guidance, never a verdict. */
export function recommendFromDraft(draft: SubmissionDraft): Recommendation {
  const all = Object.values(draft.fields).join(' ') + ' ' + draft.revenue + ' ' + draft.growth
  let score = 0
  for (const re of POSITIVE) if (re.test(all)) score += 1
  for (const re of NEGATIVE) if (re.test(all)) score -= 2
  if (/\$\s?\d|\d+\s?(so'm|som|uzs|usd)/i.test(draft.revenue)) score += 2

  const signal: Signal = score >= 4 ? 'high' : score >= 1 ? 'medium' : 'low'
  const headlines: Record<Signal, string> = {
    high: "Tez orada sinchiklab ko'rishga arziydi",
    medium: 'Istiqbolli, ammo ochiq savollar bor',
    low: "Bu pipeline uchun hali erta ko'rinadi",
  }
  const rationale: string[] = []
  rationale.push(
    /revenue|paying|daromad|mijoz/i.test(all)
      ? "Asoschi tijoriy natijalar haqida yozgan; daromad da'vosini isbot bilan solishtiring."
      : "Hali tijoriy natija ko'rsatilmagan; asosiy tayanch — bozor va jamoa.",
  )
  rationale.push(
    draft.fields.team.trim().length > 120
      ? "Jamoa bo'limi mazmunli yozilgan — tekshiruv bosqichida tavsiyalarni tekshiring."
      : "Jamoa bo'limi juda qisqa; kim qurishini va kim sotishini so'rang.",
  )
  rationale.push("Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.")
  return { signal, headline: headlines[signal], rationale }
}

/** Stable opaque id from a string seed (demo stand-in for a server UUID). */
export function opaqueId(seed: string): string {
  let h = 2166136261
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  const hex = (h >>> 0).toString(16).padStart(8, '0')
  return `st_${hex}${seed.length.toString(16)}`
}
