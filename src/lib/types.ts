/** Core domain model. The one object everywhere is a Startup (see IA doc). */

export type Role = 'founder' | 'vc'

/** Kanban stages, linear left-to-right. */
export type Stage = 'new' | 'in-review' | 'recommended' | 'advanced' | 'passed'

/** Green / yellow / red priority — ranks attention, never a verdict. */
export type Signal = 'high' | 'medium' | 'low'

/** The VC's decision on a startup. */
export type Decision = 'recommend' | 'advance' | 'pass'

export type Lang = 'en' | 'uz' | 'ru'

/** The six submission sections, in flow order. */
export const STEP_KEYS = ['problem', 'product', 'market', 'traction', 'team', 'ask'] as const
export type StepKey = (typeof STEP_KEYS)[number]

export interface FounderProfile {
  name: string
  email: string
  city: string
  language: Lang
}

export interface Attachment {
  label: string
  kind: 'deck' | 'dataroom' | 'revenue' | 'other'
  /** Demo only — no real files are stored. */
  fileName: string
}

export interface VerificationItem {
  id: string
  label: string
  hint: string
  done: boolean
}

export interface Recommendation {
  signal: Signal
  headline: string
  rationale: string[]
}

export interface Verdict {
  decision: Decision
  /** Polished English draft (source of truth, editable by the VC). */
  en: string
  /** Rendered in the founder's language. */
  local: string
  localLang: Lang
  composedAt: string
  sentAt: string | null
  edited: boolean
}

export interface Startup {
  id: string
  name: string
  oneLiner: string
  sector: string
  fundingStage: string
  founder: FounderProfile
  submittedAt: string
  stage: Stage
  signal: Signal
  /** True once a human VC re-tagged the signal (AI suggestion overridden). */
  signalOverridden: boolean
  /** AI-standardized summary, one entry per section. Simulated in this demo. */
  summary: Record<StepKey, string>
  /** The founder's raw inputs — never hidden behind the summary. */
  raw: Record<StepKey, string>
  metrics: { revenue: string; growth: string; ask: string }
  recommendation: Recommendation
  attachments: Attachment[]
  verification: VerificationItem[]
  decision: Decision | null
  /** VC's blunt private reasoning. Never shown to the founder. */
  notes: string
  verdict: Verdict | null
}

export interface SubmissionDraft {
  fields: Record<StepKey, string>
  startupName: string
  oneLiner: string
  sector: string
  fundingStage: string
  revenue: string
  growth: string
  ask: string
  attachments: Attachment[]
  /** Steps the founder has completed at least once. */
  completed: StepKey[]
  updatedAt: string | null
}

export interface Payment {
  id: string
  label: string
  amount: string
  status: 'paid' | 'failed'
  date: string
}

export interface Session {
  role: Role
  name: string
  email: string
}

export interface AppState {
  session: Session | null
  startups: Startup[]
  draft: SubmissionDraft
  /** Id of the startup created from the demo founder's own submission. */
  founderStartupId: string | null
  payments: Payment[]
}
