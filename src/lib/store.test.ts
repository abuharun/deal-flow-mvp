import { beforeEach, describe, expect, it } from 'vitest'
import { emptyDraft, initialState, loadState, reducer } from './store'
import { seedStartups } from './seed'
import { STEP_KEYS, type AppState } from './types'

function completedDraftState(): AppState {
  const state = initialState()
  const draft = emptyDraft()
  draft.startupName = 'TestCo'
  draft.oneLiner = 'Testing things'
  draft.revenue = '$5,000 / month'
  for (const k of STEP_KEYS) draft.fields[k] = `Some serious answer about ${k}. With detail.`
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
    state = reducer(state, { type: 'patch-startup', id: target.id, patch: { decision: 'recommend', notes: 'strong rev, verified' } })
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
    localStorage.setItem('oqim:v1', '{not json')
    expect(loadState().startups).toHaveLength(seededCount)
  })

  it('round-trips persisted state', () => {
    const state = reducer(initialState(), { type: 'login', role: 'vc' })
    localStorage.setItem('oqim:v1', JSON.stringify(state))
    expect(loadState().session?.role).toBe('vc')
  })
})
