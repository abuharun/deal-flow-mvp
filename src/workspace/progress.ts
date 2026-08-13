/**
 * The founder's path from a draft startup to an investor-visible dossier.
 *
 * This is a pure projection of what the API actually returned — it never
 * guesses. A step is `done` only when the backend says so (a timestamp, a row,
 * a status), `current` when it is the first unfinished step, `todo` when it is
 * still ahead, and `locked` once the founder's approval froze the startup and
 * nothing further can be changed.
 */

import type {
  AnalysisJobResponse,
  ConsentSummaryResponse,
  DeckResponse,
  NarrativeApprovalResponse,
  NarrativeCurrentResponse,
  PaymentResponse,
  StartupResponse,
} from '../api/types'

export const STEP_IDS = ['submission', 'deck', 'payment', 'consent', 'analysis', 'narrative', 'approval'] as const
export type StepId = (typeof STEP_IDS)[number]

export type StepState = 'done' | 'current' | 'todo' | 'locked'

export interface WorkspaceSnapshot {
  startup: StartupResponse
  deck: DeckResponse | null
  payment: PaymentResponse | null
  consents: ConsentSummaryResponse | null
  analysis: AnalysisJobResponse | null
  narrative: NarrativeCurrentResponse | null
  approval: NarrativeApprovalResponse | null
}

export interface StepProgress {
  id: StepId
  state: StepState
}

/** Approved startups are frozen: the backend answers 409 STARTUP_LOCKED to every edit. */
export function isLocked(startup: StartupResponse): boolean {
  return startup.status === 'vc_visible'
}

function completion(snapshot: WorkspaceSnapshot): Record<StepId, boolean> {
  const { startup, deck, payment, consents, analysis, narrative, approval } = snapshot
  return {
    submission: startup.submitted_at !== null,
    deck: deck !== null,
    payment: payment?.status === 'paid',
    consent: consents?.granted === true,
    analysis: analysis?.status === 'completed',
    // The narrative exists only once a report seeded it, so its presence is
    // itself the evidence that this step has been reached.
    narrative: narrative !== null,
    approval: approval !== null,
  }
}

/** The ordered rail the founder workspace renders. */
export function computeProgress(snapshot: WorkspaceSnapshot): StepProgress[] {
  const done = completion(snapshot)
  const locked = isLocked(snapshot.startup)
  let currentAssigned = false
  return STEP_IDS.map((id) => {
    if (done[id]) return { id, state: 'done' as const }
    // A frozen startup can no longer progress: anything unfinished stays
    // visibly locked rather than inviting an action the API will refuse.
    if (locked) return { id, state: 'locked' as const }
    if (!currentAssigned) {
      currentAssigned = true
      return { id, state: 'current' as const }
    }
    return { id, state: 'todo' as const }
  })
}

/** The step the founder should act on now, or null when everything is done. */
export function currentStep(snapshot: WorkspaceSnapshot): StepId | null {
  return computeProgress(snapshot).find((step) => step.state === 'current')?.id ?? null
}
