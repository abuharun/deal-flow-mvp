import { describe, expect, it } from 'vitest'
import { opaqueId, recommendFromDraft, summarizeField } from './simulate'
import { emptyDraft } from './store'

describe('summarizeField', () => {
  it('takes the first two sentences', () => {
    const out = summarizeField('First point here. Second point here. Third is dropped.')
    expect(out).toBe('First point here. Second point here.')
  })

  it('caps very long summaries with an ellipsis', () => {
    const out = summarizeField('word '.repeat(200) + '.', 100)
    expect(out.length).toBeLessThanOrEqual(100)
    expect(out.endsWith('…')).toBe(true)
  })

  it('handles missing input honestly', () => {
    expect(summarizeField('')).toBe('Not provided by the founder.')
  })
})

describe('recommendFromDraft', () => {
  it('reads commercial traction as high signal', () => {
    const draft = emptyDraft()
    draft.fields.traction =
      'We have 200 paying customers, revenue is growing with strong retention and signed contracts.'
    draft.fields.team = 'Two full-time founders with a decade of domain experience between them, plus four engineers hired from local unicorns.'
    draft.revenue = '$24,000 / month'
    const rec = recommendFromDraft(draft)
    expect(rec.signal).toBe('high')
    expect(rec.rationale.length).toBeGreaterThan(0)
  })

  it('reads a pre-revenue idea as low signal', () => {
    const draft = emptyDraft()
    draft.fields.traction = 'No revenue yet, idea stage.'
    const rec = recommendFromDraft(draft)
    expect(rec.signal).toBe('low')
  })

  it('always frames itself as guidance, not a verdict', () => {
    const rec = recommendFromDraft(emptyDraft())
    expect(rec.rationale.join(' ')).toMatch(/starting point/i)
  })
})

describe('opaqueId', () => {
  it('is stable for the same seed and distinct across seeds', () => {
    expect(opaqueId('xarid')).toBe(opaqueId('xarid'))
    expect(opaqueId('xarid')).not.toBe(opaqueId('tezyol'))
    expect(opaqueId('xarid')).toMatch(/^st_[0-9a-f]+$/)
  })
})
