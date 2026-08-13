/**
 * Reading the access token's claims for ROUTING ONLY.
 *
 * The signature is never checked here and must never be trusted: the browser
 * has no secret and could not verify one. The backend re-verifies signature,
 * issuer, audience, expiry AND the user's current role on every single
 * request (backend/app/deps.py), so a tampered token buys nothing but a
 * wrong-looking menu until the first API call refuses it.
 */

import type { Role } from '../api/types'

export interface AccessClaims {
  userId: string
  role: Role
  /** Absolute expiry in epoch milliseconds. */
  expiresAt: number
}

function decodeSegment(segment: string): unknown {
  const padded = segment.replace(/-/g, '+').replace(/_/g, '/')
  const json = atob(padded.padEnd(padded.length + ((4 - (padded.length % 4)) % 4), '='))
  return JSON.parse(json)
}

/** Parse the claims the UI needs, or null if the token is not usable at all. */
export function readAccessClaims(token: string): AccessClaims | null {
  const segments = token.split('.')
  if (segments.length !== 3) return null
  let payload: unknown
  try {
    payload = decodeSegment(segments[1])
  } catch {
    return null
  }
  if (typeof payload !== 'object' || payload === null) return null
  const { sub, role, exp } = payload as { sub?: unknown; role?: unknown; exp?: unknown }
  if (typeof sub !== 'string' || !sub) return null
  if (role !== 'founder' && role !== 'vc') return null
  if (typeof exp !== 'number') return null
  return { userId: sub, role, expiresAt: exp * 1000 }
}
