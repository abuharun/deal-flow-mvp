/**
 * Founder-owned resources (backend/app/routers/founder_*.py).
 *
 * Every call is bearer-authenticated and scoped server-side to the calling
 * founder: a foreign id and an unknown id both answer one canonical 404, so
 * nothing here needs (or can do) ownership checks of its own.
 */

import { request, requestBlob } from './client'
import type {
  AnalysisJobResponse,
  ConsentSummaryResponse,
  ConsentResponse,
  DeckResponse,
  NarrativeApprovalResponse,
  NarrativeCurrentResponse,
  NarrativeVersionListResponse,
  NarrativeVersionResponse,
  PaymentResponse,
  PaymentStatus,
  ReportDetailResponse,
  StartupCreateRequest,
  StartupDetailResponse,
  StartupPatchRequest,
  StartupResponse,
  SubmissionPatchRequest,
} from './types'

export interface FounderCall {
  token: string
  signal?: AbortSignal
}

const startupPath = (startupId: string) => `/founder/startups/${encodeURIComponent(startupId)}`

export function listStartups({ token, signal }: FounderCall): Promise<StartupResponse[]> {
  return request<StartupResponse[]>('/founder/startups', { token, signal })
}

export function getStartup(startupId: string, { token, signal }: FounderCall): Promise<StartupDetailResponse> {
  return request<StartupDetailResponse>(startupPath(startupId), { token, signal })
}

export function createStartup(
  payload: StartupCreateRequest,
  { token, signal }: FounderCall,
): Promise<StartupDetailResponse> {
  return request<StartupDetailResponse>('/founder/startups', { method: 'POST', json: payload, token, signal })
}

export function patchStartup(
  startupId: string,
  payload: StartupPatchRequest,
  { token, signal }: FounderCall,
): Promise<StartupResponse> {
  return request<StartupResponse>(startupPath(startupId), { method: 'PATCH', json: payload, token, signal })
}

export function patchSubmission(
  startupId: string,
  payload: SubmissionPatchRequest,
  { token, signal }: FounderCall,
): Promise<StartupDetailResponse> {
  return request<StartupDetailResponse>(`${startupPath(startupId)}/submission`, {
    method: 'PATCH',
    json: payload,
    token,
    signal,
  })
}

export function submitStartup(startupId: string, { token, signal }: FounderCall): Promise<StartupResponse> {
  return request<StartupResponse>(`${startupPath(startupId)}/submit`, { method: 'POST', token, signal })
}

export function getDeckMetadata(startupId: string, { token, signal }: FounderCall): Promise<DeckResponse> {
  return request<DeckResponse>(`${startupPath(startupId)}/deck/metadata`, { token, signal })
}

export function uploadDeck(startupId: string, file: File, { token, signal }: FounderCall): Promise<DeckResponse> {
  const form = new FormData()
  form.append('file', file, file.name)
  return request<DeckResponse>(`${startupPath(startupId)}/deck`, { method: 'PUT', form, token, signal })
}

export function deleteDeck(startupId: string, { token, signal }: FounderCall): Promise<void> {
  return request<void>(`${startupPath(startupId)}/deck`, { method: 'DELETE', token, signal })
}

export function downloadDeck(startupId: string, { token, signal }: FounderCall): Promise<Blob> {
  return requestBlob(`${startupPath(startupId)}/deck`, { token, signal })
}

export function getPayment(startupId: string, { token, signal }: FounderCall): Promise<PaymentResponse> {
  return request<PaymentResponse>(`${startupPath(startupId)}/payment`, { token, signal })
}

/** Demo payment: the founder explicitly chooses the simulated outcome. */
export function submitPayment(
  startupId: string,
  outcome: PaymentStatus,
  { token, signal }: FounderCall,
): Promise<PaymentResponse> {
  return request<PaymentResponse>(`${startupPath(startupId)}/payment`, {
    method: 'POST',
    json: { simulate_outcome: outcome },
    token,
    signal,
  })
}

export function getConsents(startupId: string, { token, signal }: FounderCall): Promise<ConsentSummaryResponse> {
  return request<ConsentSummaryResponse>(`${startupPath(startupId)}/consents`, { token, signal })
}

export function grantConsent(
  startupId: string,
  textVersion: string,
  { token, signal }: FounderCall,
): Promise<ConsentResponse> {
  return request<ConsentResponse>(`${startupPath(startupId)}/consents`, {
    method: 'POST',
    json: { kind: 'ai_privacy', text_version: textVersion },
    token,
    signal,
  })
}

export function getAnalysis(startupId: string, { token, signal }: FounderCall): Promise<AnalysisJobResponse> {
  return request<AnalysisJobResponse>(`${startupPath(startupId)}/analysis`, { token, signal })
}

export function triggerAnalysis(startupId: string, { token, signal }: FounderCall): Promise<AnalysisJobResponse> {
  return request<AnalysisJobResponse>(`${startupPath(startupId)}/analysis`, { method: 'POST', token, signal })
}

export function getReport(startupId: string, { token, signal }: FounderCall): Promise<ReportDetailResponse> {
  return request<ReportDetailResponse>(`${startupPath(startupId)}/report`, { token, signal })
}

export function getNarrative(startupId: string, { token, signal }: FounderCall): Promise<NarrativeCurrentResponse> {
  return request<NarrativeCurrentResponse>(`${startupPath(startupId)}/narrative`, { token, signal })
}

export function saveNarrative(
  startupId: string,
  content: string,
  { token, signal }: FounderCall,
): Promise<NarrativeCurrentResponse> {
  return request<NarrativeCurrentResponse>(`${startupPath(startupId)}/narrative`, {
    method: 'PATCH',
    json: { content },
    token,
    signal,
  })
}

export function listNarrativeVersions(
  startupId: string,
  { token, signal }: FounderCall,
): Promise<NarrativeVersionListResponse> {
  return request<NarrativeVersionListResponse>(`${startupPath(startupId)}/narrative/versions`, { token, signal })
}

export function getNarrativeVersion(
  startupId: string,
  version: number,
  { token, signal }: FounderCall,
): Promise<NarrativeVersionResponse> {
  return request<NarrativeVersionResponse>(`${startupPath(startupId)}/narrative/versions/${version}`, {
    token,
    signal,
  })
}

export function getApproval(startupId: string, { token, signal }: FounderCall): Promise<NarrativeApprovalResponse> {
  return request<NarrativeApprovalResponse>(`${startupPath(startupId)}/narrative/approval`, { token, signal })
}

/** Freezes the named version and makes the startup visible to investors. */
export function approveNarrative(
  startupId: string,
  version: number,
  { token, signal }: FounderCall,
): Promise<NarrativeApprovalResponse> {
  return request<NarrativeApprovalResponse>(`${startupPath(startupId)}/narrative/approval`, {
    method: 'POST',
    json: { version },
    token,
    signal,
  })
}
