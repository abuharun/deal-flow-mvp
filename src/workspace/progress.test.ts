import { describe, expect, it } from 'vitest'
import { computeProgress, currentStep, isLocked, type WorkspaceSnapshot } from './progress'
import {
  makeAnalysisJob,
  makeApproval,
  makeConsents,
  makeDeck,
  makeNarrative,
  makePayment,
  makeStartup,
} from '../test/factories'

function snapshot(overrides: Partial<WorkspaceSnapshot> = {}): WorkspaceSnapshot {
  return {
    startup: makeStartup(),
    deck: null,
    payment: null,
    consents: null,
    analysis: null,
    narrative: null,
    approval: null,
    ...overrides,
  }
}

const stateOf = (snap: WorkspaceSnapshot, id: string) =>
  computeProgress(snap).find((step) => step.id === id)!.state

describe('computeProgress', () => {
  it('points a brand-new startup at its questionnaire and nothing else', () => {
    const steps = computeProgress(snapshot())
    expect(steps.map((step) => step.state)).toEqual(['current', 'todo', 'todo', 'todo', 'todo', 'todo', 'todo'])
    expect(currentStep(snapshot())).toBe('submission')
  })

  it('marks submission done only once the backend recorded submitted_at', () => {
    expect(stateOf(snapshot(), 'submission')).toBe('current')
    const submitted = snapshot({ startup: makeStartup({ status: 'submitted', submitted_at: '2026-07-21T09:00:00Z' }) })
    expect(stateOf(submitted, 'submission')).toBe('done')
    expect(currentStep(submitted)).toBe('deck')
  })

  /** Everything before `payment` finished, so later steps are the ones under test. */
  const throughDeck = (overrides: Partial<WorkspaceSnapshot> = {}) =>
    snapshot({
      startup: makeStartup({ status: 'submitted', submitted_at: '2026-07-21T09:00:00Z' }),
      deck: makeDeck(),
      ...overrides,
    })

  it('counts a failed demo payment as unfinished, never as progress', () => {
    const failed = throughDeck({ payment: makePayment({ status: 'failed', paid_at: null }) })
    expect(stateOf(failed, 'payment')).toBe('current')
    expect(stateOf(throughDeck({ payment: makePayment() }), 'payment')).toBe('done')
  })

  it('treats consent as given only for the current text version the API reports', () => {
    const base = (consents: WorkspaceSnapshot['consents']) => throughDeck({ payment: makePayment(), consents })
    expect(stateOf(base(makeConsents({ granted: false, history: [] })), 'consent')).toBe('current')
    expect(stateOf(base(makeConsents()), 'consent')).toBe('done')
  })

  const throughConsent = (analysis: WorkspaceSnapshot['analysis']) =>
    throughDeck({ payment: makePayment(), consents: makeConsents(), analysis })

  it.each([['queued'], ['running'], ['retrying'], ['failed']] as const)(
    'leaves analysis unfinished while the job is %s',
    (status) => {
      expect(stateOf(throughConsent(makeAnalysisJob({ status })), 'analysis')).toBe('current')
    },
  )

  it('completes analysis when the job completed', () => {
    expect(stateOf(throughConsent(makeAnalysisJob({ status: 'completed' })), 'analysis')).toBe('done')
  })

  it('walks the whole path in order as each backend fact arrives', () => {
    const full = snapshot({
      startup: makeStartup({ status: 'report_ready', submitted_at: '2026-07-21T09:00:00Z' }),
      deck: makeDeck(),
      payment: makePayment(),
      consents: makeConsents(),
      analysis: makeAnalysisJob({ status: 'completed' }),
      narrative: makeNarrative(),
    })
    expect(computeProgress(full).map((step) => `${step.id}:${step.state}`)).toEqual([
      'submission:done',
      'deck:done',
      'payment:done',
      'consent:done',
      'analysis:done',
      'narrative:done',
      'approval:current',
    ])
  })

  it('locks every unfinished step once the startup is visible to investors', () => {
    const approved = snapshot({
      startup: makeStartup({ status: 'vc_visible', submitted_at: '2026-07-21T09:00:00Z', vc_visible_at: '2026-07-23T09:00:00Z' }),
      approval: makeApproval(),
    })
    expect(isLocked(approved.startup)).toBe(true)
    expect(stateOf(approved, 'deck')).toBe('locked')
    expect(stateOf(approved, 'approval')).toBe('done')
    expect(currentStep(approved)).toBeNull()
  })

  it('does not treat a draft startup as locked', () => {
    expect(isLocked(makeStartup())).toBe(false)
    expect(isLocked(makeStartup({ status: 'report_ready' }))).toBe(false)
  })
})
