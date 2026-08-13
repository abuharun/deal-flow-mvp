/**
 * Test fixtures shaped exactly like the backend's real responses.
 *
 * Every factory mirrors a schema in backend/app/schemas — tests must never
 * assert against a shape the API cannot actually produce.
 */

import type {
  AnalysisJobResponse,
  ConsentSummaryResponse,
  DeckResponse,
  NarrativeApprovalResponse,
  NarrativeCurrentResponse,
  PaymentResponse,
  ReportDetailResponse,
  Role,
  StartupDetailResponse,
  StartupResponse,
  SubmissionResponse,
  UserSummary,
  VcStartupDossierResponse,
  VcStartupSummary,
} from '../api/types'

const base64url = (value: string) =>
  btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

/**
 * A structurally valid HS256-shaped access token. The signature is a
 * placeholder: the frontend only ever reads claims for routing, and the real
 * backend re-verifies every token it is presented with.
 */
export function makeAccessToken(
  claims: { sub?: string; role?: Role; expiresInSeconds?: number } = {},
): string {
  const { sub = 'user-1', role = 'founder', expiresInSeconds = 900 } = claims
  const payload = {
    sub,
    role,
    jti: 'jti-1',
    typ: 'access',
    iss: 'bevosita-api',
    aud: 'bevosita-web',
    iat: Math.floor(Date.now() / 1000),
    nbf: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + expiresInSeconds,
  }
  return `${base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))}.${base64url(JSON.stringify(payload))}.sig`
}

export function makeUser(overrides: Partial<UserSummary> = {}): UserSummary {
  return {
    id: 'user-1',
    email: 'aziza@bevosita.test',
    full_name: 'Aziza Karimova',
    role: 'founder',
    locale: 'uz',
    ...overrides,
  }
}

export function makeStartup(overrides: Partial<StartupResponse> = {}): StartupResponse {
  return {
    id: 'startup-1',
    name: 'Xarid',
    one_liner: "Restoran va kafelar uchun B2B ta'minot marketpleysi",
    sector: 'Marketplace',
    funding_stage: 'Seed',
    city: 'Toshkent',
    status: 'draft',
    input_revision: 1,
    submitted_at: null,
    vc_visible_at: null,
    created_at: '2026-07-20T09:00:00Z',
    updated_at: '2026-07-20T09:00:00Z',
    ...overrides,
  }
}

export function makeStartupDetail(
  overrides: Partial<StartupResponse> & { submission?: Partial<SubmissionResponse> } = {},
): StartupDetailResponse {
  const { submission, ...rest } = overrides
  return {
    ...makeStartup(rest),
    submission: {
      problem: '',
      product: '',
      market: '',
      traction: '',
      team: '',
      ask: '',
      revenue: null,
      growth: null,
      ask_amount: null,
      dataroom_url: null,
      completed_steps: [],
      updated_at: '2026-07-20T09:00:00Z',
      ...submission,
    },
  }
}

export function makeDeck(overrides: Partial<DeckResponse> = {}): DeckResponse {
  return {
    id: 'deck-1',
    filename: 'xarid-deck.pdf',
    mime_type: 'application/pdf',
    size_bytes: 482_311,
    sha256: 'a'.repeat(64),
    page_count: 12,
    uploaded_at: '2026-07-21T10:00:00Z',
    ...overrides,
  }
}

export function makePayment(overrides: Partial<PaymentResponse> = {}): PaymentResponse {
  return {
    id: 'pay-1',
    mode: 'demo',
    status: 'paid',
    label: 'demo_validation_fee',
    paid_at: '2026-07-21T11:00:00Z',
    created_at: '2026-07-21T11:00:00Z',
    updated_at: '2026-07-21T11:00:00Z',
    ...overrides,
  }
}

export function makeConsents(overrides: Partial<ConsentSummaryResponse> = {}): ConsentSummaryResponse {
  return {
    current_version: 'ai-privacy.v1',
    granted: true,
    history: [
      { id: 'consent-1', kind: 'ai_privacy', text_version: 'ai-privacy.v1', granted_at: '2026-07-21T11:05:00Z' },
    ],
    ...overrides,
  }
}

export function makeAnalysisJob(overrides: Partial<AnalysisJobResponse> = {}): AnalysisJobResponse {
  return {
    id: 'job-1',
    startup_id: 'startup-1',
    input_revision: 1,
    status: 'queued',
    attempts: 0,
    max_attempts: 3,
    queued_at: '2026-07-21T11:10:00Z',
    started_at: null,
    finished_at: null,
    next_attempt_at: null,
    last_error_code: null,
    last_error_message_key: null,
    stale: false,
    created_at: '2026-07-21T11:10:00Z',
    updated_at: '2026-07-21T11:10:00Z',
    ...overrides,
  }
}

const REPORT_BODY = {
  executive_summary: 'Xarid supplies Tashkent restaurants through a B2B marketplace.',
  sections: {
    uzbekistan_central_asia_market: { narrative: 'Tashkent food service is fragmented.', citation_ids: [1] },
    global_competitors: { narrative: 'Comparable models exist in Turkey and India.', citation_ids: [2] },
    us_vc_readiness: { narrative: 'Metrics reporting needs tightening.', citation_ids: [3] },
  },
  competitors: [{ name: 'Getir', region: 'Turkey', note: 'Rapid grocery delivery', citation_ids: [2] }],
  claims: [
    { statement: 'Gross revenue is $24.7k per month.', support: 'founder_provided' as const, citation_ids: [], confidence: 'medium' as const },
    { statement: 'The B2B food distribution market is fragmented.', support: 'cited' as const, citation_ids: [1], confidence: 'high' as const },
  ],
  contradictions: ['The deck states 400 clients; the questionnaire states 240.'],
  unsupported_claims: ['Regional expansion timeline has no evidence.'],
  readiness_checklist: [
    { item: 'clean_cap_table', status: 'unknown' as const, confidence: 'low' as const, evidence: [], evidence_gap: 'No cap table supplied.' },
    { item: 'revenue_evidence', status: 'partially_met' as const, confidence: 'medium' as const, evidence: [3], evidence_gap: null },
  ],
}

const REPORT_SOURCES = [
  {
    ordinal: 1,
    url: 'https://stat.uz/en/food-service',
    title: 'Uzbekistan food service statistics',
    published_date: '2026-02-01',
    accessed_date: '2026-07-22',
    source_quality: 'primary' as const,
    confidence: 'high' as const,
    snippet: 'Food service spending grew 18% year on year.',
  },
  {
    ordinal: 2,
    url: 'https://example.com/getir-analysis',
    title: 'Rapid commerce in emerging markets',
    published_date: null,
    accessed_date: '2026-07-22',
    source_quality: 'reputable_media' as const,
    confidence: 'medium' as const,
    snippet: null,
  },
  {
    ordinal: 3,
    url: 'https://example.com/us-vc-readiness',
    title: 'What US seed investors expect',
    published_date: '2025-11-11',
    accessed_date: '2026-07-22',
    source_quality: 'industry' as const,
    confidence: 'medium' as const,
    snippet: 'Monthly cohort retention is the first metric requested.',
  },
]

export function makeReport(overrides: Partial<ReportDetailResponse> = {}): ReportDetailResponse {
  return {
    id: 'report-1',
    startup_id: 'startup-1',
    schema_version: 'report.v1',
    language: 'en',
    report: { ...REPORT_BODY, pitch_narrative_draft: 'Xarid connects restaurants to vetted suppliers.' },
    sources: REPORT_SOURCES,
    model: 'gpt-4o-mini',
    prompt_version: 'analysis.v1',
    partial: false,
    evidence_count: 3,
    input_revision: 1,
    generated_at: '2026-07-22T08:00:00Z',
    created_at: '2026-07-22T08:00:00Z',
    stale: false,
    ...overrides,
  }
}

export function makeNarrative(overrides: Partial<NarrativeCurrentResponse> = {}): NarrativeCurrentResponse {
  return {
    startup_id: 'startup-1',
    version: 1,
    content: 'Xarid connects restaurants to vetted suppliers.',
    source: 'report_seed',
    report_id: 'report-1',
    input_revision: 1,
    created_at: '2026-07-22T08:05:00Z',
    updated_at: '2026-07-22T08:05:00Z',
    ...overrides,
  }
}

export function makeApproval(overrides: Partial<NarrativeApprovalResponse> = {}): NarrativeApprovalResponse {
  return {
    startup_id: 'startup-1',
    narrative_version_id: 'version-2',
    version: 2,
    content: 'Xarid connects restaurants to vetted suppliers, verified weekly.',
    source: 'founder_edit',
    report_id: 'report-1',
    input_revision: 1,
    approved_by: 'user-1',
    approved_at: '2026-07-23T09:00:00Z',
    status: 'vc_visible',
    vc_visible_at: '2026-07-23T09:00:00Z',
    ...overrides,
  }
}

export function makeVcSummary(overrides: Partial<VcStartupSummary> = {}): VcStartupSummary {
  return {
    id: 'startup-1',
    name: 'Xarid',
    one_liner: "Restoran va kafelar uchun B2B ta'minot marketpleysi",
    sector: 'Marketplace',
    funding_stage: 'Seed',
    city: 'Toshkent',
    vc_visible_at: '2026-07-23T09:00:00Z',
    approved_at: '2026-07-23T09:00:00Z',
    ...overrides,
  }
}

export function makeDossier(overrides: Partial<VcStartupDossierResponse> = {}): VcStartupDossierResponse {
  return {
    startup: makeVcSummary(),
    narrative: {
      version: 2,
      content: 'Xarid connects restaurants to vetted suppliers, verified weekly.',
      approved_at: '2026-07-23T09:00:00Z',
    },
    report: {
      schema_version: 'report.v1',
      language: 'en',
      report: REPORT_BODY,
      sources: REPORT_SOURCES,
      partial: false,
      evidence_count: 3,
      generated_at: '2026-07-22T08:00:00Z',
    },
    ...overrides,
  }
}
