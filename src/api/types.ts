/**
 * Typed mirrors of the FastAPI response contracts (backend/app/schemas/*).
 *
 * These are transcriptions of what the backend actually returns — nothing is
 * invented here. Field names stay snake_case exactly as they arrive on the
 * wire, so a drift between backend and frontend surfaces as a type error at
 * the call site instead of an undefined at runtime.
 */

export type Role = 'founder' | 'vc'
export type UiLocale = 'uz' | 'ru'

/** backend/app/schemas/auth.py: UserSummary */
export interface UserSummary {
  id: string
  email: string
  full_name: string
  role: Role
  locale: UiLocale
}

/** backend/app/schemas/auth.py: LoginResponse */
export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserSummary
}

/** backend/app/schemas/auth.py: AccessTokenResponse (refresh carries no user) */
export interface AccessTokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

/** backend/app/models/startup.py: StartupStatus */
export type StartupStatus = 'draft' | 'submitted' | 'analyzing' | 'report_ready' | 'vc_visible'

/** backend/app/schemas/startup.py: SubmissionResponse */
export interface SubmissionResponse {
  problem: string
  product: string
  market: string
  traction: string
  team: string
  ask: string
  revenue: string | null
  growth: string | null
  ask_amount: number | null
  dataroom_url: string | null
  completed_steps: string[]
  updated_at: string
}

/** backend/app/schemas/startup.py: StartupResponse */
export interface StartupResponse {
  id: string
  name: string
  one_liner: string
  sector: string
  funding_stage: string
  city: string
  status: StartupStatus
  input_revision: number
  submitted_at: string | null
  vc_visible_at: string | null
  created_at: string
  updated_at: string
}

/** backend/app/schemas/startup.py: StartupDetailResponse */
export interface StartupDetailResponse extends StartupResponse {
  submission: SubmissionResponse
}

/** The six answer fields the backend stores 1:1 with a startup. */
export const ANSWER_KEYS = ['problem', 'product', 'market', 'traction', 'team', 'ask'] as const
export type AnswerKey = (typeof ANSWER_KEYS)[number]

export interface StartupCreateRequest {
  name: string
  one_liner?: string
  sector?: string
  funding_stage?: string
  city?: string
}

/** Partial metadata update; absent keys are left untouched (never null). */
export type StartupPatchRequest = Partial<Record<'name' | 'one_liner' | 'sector' | 'funding_stage' | 'city', string>>

export interface SubmissionPatchRequest {
  problem?: string
  product?: string
  market?: string
  traction?: string
  team?: string
  ask?: string
  revenue?: string | null
  growth?: string | null
  ask_amount?: number | null
  dataroom_url?: string | null
  completed_steps?: string[]
}

/** backend/app/schemas/deck.py: DeckResponse */
export interface DeckResponse {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  page_count: number
  uploaded_at: string
}

/** backend/app/schemas/payment.py: PaymentResponse — mode is always 'demo'. */
export type PaymentStatus = 'paid' | 'failed'

export interface PaymentResponse {
  id: string
  mode: string
  status: string
  label: string
  paid_at: string | null
  created_at: string
  updated_at: string
}

/** backend/app/schemas/consent.py */
export interface ConsentResponse {
  id: string
  kind: string
  text_version: string
  granted_at: string
}

export interface ConsentSummaryResponse {
  current_version: string
  granted: boolean
  history: ConsentResponse[]
}

/** backend/app/models/analysis_job.py: ALL_STATUSES */
export type AnalysisStatus = 'queued' | 'running' | 'retrying' | 'completed' | 'failed'

/** backend/app/schemas/analysis.py: AnalysisJobResponse */
export interface AnalysisJobResponse {
  id: string
  startup_id: string
  input_revision: number
  status: AnalysisStatus
  attempts: number
  max_attempts: number
  queued_at: string
  started_at: string | null
  finished_at: string | null
  next_attempt_at: string | null
  last_error_code: string | null
  last_error_message_key: string | null
  stale: boolean
  created_at: string
  updated_at: string
}

/** backend/app/services/ai_precondition.py: AiPreconditionReason values */
export const PRECONDITION_REASONS = [
  'startup_not_submitted',
  'deck_missing',
  'payment_not_paid',
  'consent_missing',
] as const
export type PreconditionReason = (typeof PRECONDITION_REASONS)[number]

/** backend/app/schemas/report.py */
export type SourceQuality = 'primary' | 'reputable_media' | 'industry' | 'blog' | 'unknown'
export type Confidence = 'high' | 'medium' | 'low'
export type ClaimSupport = 'cited' | 'founder_provided' | 'assumption'
export type ChecklistStatus = 'met' | 'partially_met' | 'not_met' | 'unknown'

export interface ReportSection {
  narrative: string
  citation_ids: number[]
}

export interface ReportSections {
  uzbekistan_central_asia_market: ReportSection
  global_competitors: ReportSection
  us_vc_readiness: ReportSection
}

export interface ReportCompetitor {
  name: string
  region: string
  note: string
  citation_ids: number[]
}

export interface ReportClaim {
  statement: string
  support: ClaimSupport
  citation_ids: number[]
  confidence: Confidence
}

export interface ReportChecklistItem {
  item: string
  status: ChecklistStatus
  confidence: Confidence
  evidence: number[]
  evidence_gap: string | null
}

/** The report body an investor reads: report.v1 minus pitch_narrative_draft. */
export interface VcReportBody {
  executive_summary: string
  sections: ReportSections
  competitors: ReportCompetitor[]
  claims: ReportClaim[]
  contradictions: string[]
  unsupported_claims: string[]
  readiness_checklist: ReportChecklistItem[]
}

/** The founder's report body additionally carries the AI's narrative draft. */
export interface ReportBody extends VcReportBody {
  pitch_narrative_draft: string
}

export interface ReportSourceResponse {
  ordinal: number
  url: string
  title: string
  published_date: string | null
  accessed_date: string
  source_quality: SourceQuality
  confidence: Confidence
  snippet: string | null
}

/** backend/app/schemas/report.py: ReportDetailResponse */
export interface ReportDetailResponse {
  id: string
  startup_id: string
  schema_version: string
  language: string
  report: ReportBody
  sources: ReportSourceResponse[]
  model: string
  prompt_version: string
  partial: boolean
  evidence_count: number | null
  input_revision: number
  generated_at: string
  created_at: string
  stale: boolean
}

/** backend/app/schemas/narrative.py */
export type NarrativeSource = 'report_seed' | 'founder_edit'

export interface NarrativeCurrentResponse {
  startup_id: string
  version: number
  content: string
  source: NarrativeSource
  report_id: string
  input_revision: number
  created_at: string
  updated_at: string
}

export interface NarrativeVersionResponse {
  version: number
  content: string
  source: NarrativeSource
  report_id: string
  input_revision: number
  created_at: string
}

export interface NarrativeVersionSummary {
  version: number
  source: NarrativeSource
  report_id: string
  input_revision: number
  content_length: number
  created_at: string
}

export interface NarrativeVersionListResponse {
  current_version: number
  versions: NarrativeVersionSummary[]
}

/** backend/app/schemas/narrative_approval.py: NarrativeApprovalResponse */
export interface NarrativeApprovalResponse {
  startup_id: string
  narrative_version_id: string
  version: number
  content: string
  source: NarrativeSource
  report_id: string
  input_revision: number
  approved_by: string
  approved_at: string
  status: StartupStatus
  vc_visible_at: string
}

/** backend/app/schemas/vc.py */
export interface VcStartupSummary {
  id: string
  name: string
  one_liner: string
  sector: string
  funding_stage: string
  city: string
  vc_visible_at: string
  approved_at: string
}

export interface VcStartupListResponse {
  items: VcStartupSummary[]
  limit: number
  offset: number
  total: number
}

export interface VcApprovedNarrative {
  version: number
  content: string
  approved_at: string
}

export interface VcReport {
  schema_version: string
  language: string
  report: VcReportBody
  sources: ReportSourceResponse[]
  partial: boolean
  evidence_count: number | null
  generated_at: string
}

export interface VcStartupDossierResponse {
  startup: VcStartupSummary
  narrative: VcApprovedNarrative
  report: VcReport
}
