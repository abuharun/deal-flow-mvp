import { beforeEach, describe, expect, it } from 'vitest'
import { emptyDraft, initialState, loadState, reducer } from './store'
import { seedStartups } from './seed'
import { formatDate, formatDateLong } from './format'
import { STEP_KEYS, type AppState } from './types'

function completedDraftState(): AppState {
  const state = initialState()
  const draft = emptyDraft()
  draft.startupName = 'TestCo'
  draft.oneLiner = 'Sinov uchun mahsulot'
  draft.revenue = '$5,000 / oy'
  for (const k of STEP_KEYS) draft.fields[k] = `${k} haqida jiddiy javob. Tafsilotlari bilan.`
  draft.completed = [...STEP_KEYS]
  return { ...state, draft, session: { role: 'founder', name: 'F', email: 'f@x' } }
}

describe('reducer', () => {
  it('login resolves the demo identity for each role', () => {
    const vc = reducer(initialState(), { type: 'login', role: 'vc' })
    expect(vc.session?.role).toBe('vc')
    const founder = reducer(initialState(), { type: 'login', role: 'founder' })
    expect(founder.session?.role).toBe('founder')
  })

  it('successful payment submits the startup into the pipeline as New', () => {
    const before = completedDraftState()
    const after = reducer(before, { type: 'payment', ok: true })
    expect(after.startups).toHaveLength(before.startups.length + 1)
    expect(after.founderStartupId).not.toBeNull()
    const created = after.startups.find((s) => s.id === after.founderStartupId)!
    expect(created.name).toBe('TestCo')
    expect(created.stage).toBe('new')
    expect(created.raw.problem).toContain('problem')
    expect(after.payments[0].status).toBe('paid')
    expect(after.payments[0].label).toContain("Baholash to'lovi")
  })

  it('failed payment holds the founder at the pay step — nothing submitted', () => {
    const before = completedDraftState()
    const after = reducer(before, { type: 'payment', ok: false })
    expect(after.startups).toHaveLength(before.startups.length)
    expect(after.founderStartupId).toBeNull()
    expect(after.payments[0].status).toBe('failed')
  })

  it('toggle-verification flips a single checklist item', () => {
    const state = initialState()
    const target = state.startups[0]
    const after = reducer(state, { type: 'toggle-verification', id: target.id, itemId: 'revenue' })
    const item = after.startups[0].verification.find((v) => v.id === 'revenue')!
    expect(item.done).toBe(true)
    expect(after.startups[0].verification.filter((v) => v.done)).toHaveLength(1)
  })

  it('compose → edit → send moves the startup to the decision stage', () => {
    let state = initialState()
    const target = state.startups.find((s) => s.stage === 'new')!
    state = reducer(state, { type: 'patch-startup', id: target.id, patch: { decision: 'recommend', notes: 'daromad kuchli, tasdiqlandi' } })
    state = reducer(state, { type: 'compose-verdict', id: target.id })
    let s = state.startups.find((x) => x.id === target.id)!
    expect(s.verdict).not.toBeNull()
    expect(s.verdict!.sentAt).toBeNull()
    expect(s.verdict!.en).toContain('Our reasoning:')

    state = reducer(state, { type: 'edit-verdict', id: target.id, en: s.verdict!.en + '\nP.S. Call me.' })
    s = state.startups.find((x) => x.id === target.id)!
    expect(s.verdict!.edited).toBe(true)

    state = reducer(state, { type: 'send-verdict', id: target.id })
    s = state.startups.find((x) => x.id === target.id)!
    expect(s.verdict!.sentAt).not.toBeNull()
    expect(s.stage).toBe('recommended')
  })

  it('compose without a decision is a no-op — the human decides first', () => {
    const state = initialState()
    const target = state.startups.find((s) => s.stage === 'new')!
    const after = reducer(state, { type: 'compose-verdict', id: target.id })
    expect(after.startups.find((x) => x.id === target.id)!.verdict).toBeNull()
  })

  it('reset restores seed data but keeps the session', () => {
    let state = completedDraftState()
    state = reducer(state, { type: 'payment', ok: true })
    const after = reducer(state, { type: 'reset' })
    expect(after.founderStartupId).toBeNull()
    expect(after.draft.startupName).toBe('')
    expect(after.session?.role).toBe('founder')
  })
})

describe('loadState', () => {
  beforeEach(() => localStorage.clear())

  it('falls back to seeded state when storage is empty or corrupt', () => {
    const seededCount = seedStartups().length
    expect(seededCount).toBeGreaterThan(0)
    expect(loadState().startups).toHaveLength(seededCount)
    localStorage.setItem('oqim:v2', '{not json')
    expect(loadState().startups).toHaveLength(seededCount)
  })

  it('seeds Uzbek content', () => {
    const xarid = loadState().startups.find((s) => s.name === 'Xarid')!
    expect(xarid.raw.problem).toContain('Toshkentdagi restoranlar')
  })

  it('round-trips persisted state', () => {
    const state = reducer(initialState(), { type: 'login', role: 'vc' })
    localStorage.setItem('oqim:v2', JSON.stringify(state))
    expect(loadState().session?.role).toBe('vc')
  })

  it('migrates legacy demo emails and generated branding without losing business state', () => {
    const state = reducer(initialState(), { type: 'login', role: 'vc' })
    state.session!.email = 'laylo@oqim.demo'
    state.startups[0] = {
      ...state.startups[0],
      stage: 'in-review',
      notes: 'Keep this partner note exactly.',
      founder: { ...state.startups[0].founder, email: 'dilshod@oqim.demo' },
      verdict: {
        decision: 'recommend',
        en: 'Reviewed through Oqim.',
        local: 'Oqim orqali ko‘rib chiqildi.',
        localLang: 'uz',
        composedAt: '2026-07-29T00:00:00Z',
        sentAt: null,
        edited: false,
      },
    }
    localStorage.setItem('oqim:v2', JSON.stringify(state))

    const loaded = loadState()
    expect(loaded.session?.email).toBe('laylo@bevosita.demo')
    expect(loaded.startups[0].founder.email).toBe('dilshod@bevosita.demo')
    expect(loaded.startups[0].verdict?.en).toBe('Reviewed through Bevosita.')
    expect(loaded.startups[0].verdict?.local).toBe('Bevosita orqali ko‘rib chiqildi.')
    expect(loaded.startups[0].stage).toBe('in-review')
    expect(loaded.startups[0].notes).toBe('Keep this partner note exactly.')
  })

  it('migrates a legacy v1 entry: session kept, content reseeded, old key removed', () => {
    const legacy = reducer(initialState(), { type: 'login', role: 'vc' })
    localStorage.setItem('oqim:v1', JSON.stringify(legacy))
    const state = loadState()
    expect(state.session?.role).toBe('vc')
    expect(state.startups).toHaveLength(seedStartups().length)
    // The stale English seed content is replaced by the current Uzbek seed.
    expect(state.startups.find((s) => s.name === 'Xarid')!.raw.problem).toContain('Toshkentdagi restoranlar')
    expect(localStorage.getItem('oqim:v1')).toBeNull()
  })

  it('drops a corrupt legacy v1 entry without breaking the app', () => {
    localStorage.setItem('oqim:v1', '{not json')
    const state = loadState()
    expect(state.session).toBeNull()
    expect(state.startups).toHaveLength(seedStartups().length)
    expect(localStorage.getItem('oqim:v1')).toBeNull()
  })
})

describe('formatDate / formatDateLong', () => {
  it('renders short Uzbek month names deterministically', () => {
    expect(formatDate('2026-07-26T12:00:00')).toBe('26-iyl, 2026')
    expect(formatDate('2026-01-05T12:00:00')).toBe('5-yan, 2026')
    expect(formatDate('2025-12-31T12:00:00')).toBe('31-dek, 2025')
  })

  it('renders full Uzbek month names for long dates', () => {
    expect(formatDateLong('2026-07-26T12:00:00')).toBe('26-iyul, 2026')
    expect(formatDateLong('2026-09-03T12:00:00')).toBe('3-sentabr, 2026')
    expect(formatDateLong('2026-02-14T12:00:00')).toBe('14-fevral, 2026')
  })

  it('never emits Intl fallback placeholders like "2026 M07 26"', () => {
    expect(formatDate('2026-07-26T12:00:00')).not.toMatch(/M\d{2}/)
    expect(formatDateLong('2026-07-26T12:00:00')).not.toMatch(/M\d{2}/)
  })

  it('handles invalid dates safely', () => {
    expect(formatDate('not-a-date')).toBe('—')
    expect(formatDate('')).toBe('—')
    expect(formatDateLong('not-a-date')).toBe('—')
  })
})
