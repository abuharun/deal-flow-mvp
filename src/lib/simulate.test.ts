import { describe, expect, it } from 'vitest'
import { opaqueId, recommendFromDraft, summarizeField } from './simulate'
import { emptyDraft } from './store'

describe('summarizeField', () => {
  it('takes the first two sentences', () => {
    const out = summarizeField('Birinchi fikr shu yerda. Ikkinchi fikr shu yerda. Uchinchisi tushib qoladi.')
    expect(out).toBe('Birinchi fikr shu yerda. Ikkinchi fikr shu yerda.')
  })

  it('caps very long summaries with an ellipsis', () => {
    const out = summarizeField("so'z ".repeat(200) + '.', 100)
    expect(out.length).toBeLessThanOrEqual(100)
    expect(out.endsWith('…')).toBe(true)
  })

  it('handles missing input honestly, in Uzbek', () => {
    expect(summarizeField('')).toBe("Asoschi tomonidan to'ldirilmagan.")
  })
})

describe('recommendFromDraft', () => {
  it('reads Uzbek-language commercial traction as high signal', () => {
    const draft = emptyDraft()
    draft.fields.traction =
      "200 ta to'lovchi mijozimiz bor, daromad o'sib bormoqda va uchta yirik shartnoma imzolangan."
    draft.fields.team =
      "Ikkala asoschi to'liq stavkada, o'n yillik soha tajribasiga ega, yana to'rt muhandis mahalliy unikornlardan yollangan."
    draft.revenue = '$24,000 / oy'
    const rec = recommendFromDraft(draft)
    expect(rec.signal).toBe('high')
    expect(rec.rationale.length).toBeGreaterThan(0)
  })

  it('still understands English-language traction', () => {
    const draft = emptyDraft()
    draft.fields.traction =
      'We have 200 paying customers, revenue is growing with strong retention and signed contracts.'
    draft.fields.team =
      'Two full-time founders with a decade of domain experience between them, plus four engineers hired from local unicorns.'
    draft.revenue = '$24,000 / month'
    const rec = recommendFromDraft(draft)
    expect(rec.signal).toBe('high')
  })

  it('reads a pre-revenue idea as low signal', () => {
    const draft = emptyDraft()
    draft.fields.traction = "Hali daromad yo'q, g'oya bosqichi."
    const rec = recommendFromDraft(draft)
    expect(rec.signal).toBe('low')
  })

  it('always frames itself as guidance, not a verdict', () => {
    const rec = recommendFromDraft(emptyDraft())
    expect(rec.rationale.join(' ')).toMatch(/boshlang'ich nuqta/i)
  })
})

describe('opaqueId', () => {
  it('is stable for the same seed and distinct across seeds', () => {
    expect(opaqueId('xarid')).toBe(opaqueId('xarid'))
    expect(opaqueId('xarid')).not.toBe(opaqueId('tezyol'))
    expect(opaqueId('xarid')).toMatch(/^st_[0-9a-f]+$/)
  })
})
