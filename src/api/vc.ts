/**
 * The investor's read-only surface (backend/app/routers/vc_startups.py).
 *
 * Two GETs, no writes anywhere: an investor reads founder-approved startups
 * and their frozen dossiers, and can change nothing.
 */

import { request } from './client'
import type { VcStartupDossierResponse, VcStartupListResponse } from './types'

export interface VcCall {
  token: string
  signal?: AbortSignal
}

export const VC_PAGE_SIZE = 20

export function listApprovedStartups(
  { token, signal }: VcCall,
  page: { limit?: number; offset?: number } = {},
): Promise<VcStartupListResponse> {
  const params = new URLSearchParams({
    limit: String(page.limit ?? VC_PAGE_SIZE),
    offset: String(page.offset ?? 0),
  })
  return request<VcStartupListResponse>(`/vc/startups?${params}`, { token, signal })
}

export function getDossier(startupId: string, { token, signal }: VcCall): Promise<VcStartupDossierResponse> {
  return request<VcStartupDossierResponse>(`/vc/startups/${encodeURIComponent(startupId)}`, { token, signal })
}
