/**
 * The public auth surface (backend/app/routers/auth.py).
 *
 * `refresh` and `logout` are the only calls that carry the HttpOnly refresh
 * cookie; both are also Origin-checked server-side, which the browser
 * satisfies automatically for same-site requests from the app's own origin.
 */

import { request } from './client'
import type { AccessTokenResponse, LoginResponse, UiLocale } from './types'

export function login(email: string, password: string, signal?: AbortSignal): Promise<LoginResponse> {
  return request<LoginResponse>('/auth/login', { method: 'POST', json: { email, password }, signal })
}

/** Rotate the refresh cookie into a fresh access token. */
export function refresh(signal?: AbortSignal): Promise<AccessTokenResponse> {
  return request<AccessTokenResponse>('/auth/refresh', { method: 'POST', withCredentials: true, signal })
}

/** Revoke the whole session family. Idempotent and silent by contract. */
export function logout(signal?: AbortSignal): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST', withCredentials: true, signal })
}

export interface ActivateInvitePayload {
  token: string
  email: string
  password: string
  full_name: string
  locale: UiLocale
}

/** Bevosita accounts are invite-only: this is the entire signup path. */
export function activateInvite(payload: ActivateInvitePayload, signal?: AbortSignal): Promise<void> {
  return request<void>('/auth/activate-invite', { method: 'POST', json: payload, signal })
}

export function verifyEmail(token: string, signal?: AbortSignal): Promise<void> {
  return request<void>('/auth/verify-email', { method: 'POST', json: { token }, signal })
}

/** Always answers 202 — the response is never an account-existence oracle. */
export function forgotPassword(email: string, signal?: AbortSignal): Promise<void> {
  return request<void>('/auth/forgot-password', { method: 'POST', json: { email }, signal })
}

export function resetPassword(token: string, newPassword: string, signal?: AbortSignal): Promise<void> {
  return request<void>('/auth/reset-password', {
    method: 'POST',
    json: { token, new_password: newPassword },
    signal,
  })
}
