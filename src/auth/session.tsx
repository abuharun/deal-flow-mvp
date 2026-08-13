/**
 * The browser's authenticated session.
 *
 * Token handling, deliberately:
 * - The ACCESS token lives in memory only (a ref plus render state). It is
 *   never written to localStorage, sessionStorage, a cookie, or the URL, so a
 *   stored-XSS payload has no persisted credential to steal and closing the
 *   tab ends its usefulness.
 * - The REFRESH token is an HttpOnly, Secure, SameSite=None cookie scoped to
 *   `/auth` that this code can never read. Restoring a session after a reload
 *   is therefore a server round-trip (`POST /auth/refresh`), not a storage
 *   read.
 * - The only thing cached in localStorage is the user's own display profile
 *   (name, email, locale) — no credential — and it is discarded unless the
 *   token that arrives alongside it names the same user and role.
 *
 * Nothing here decides what a user may do: the role drives which chrome
 * renders, while every actual permission is enforced by the API.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
import type { Role, UserSummary } from '../api/types'
import { readAccessClaims } from './claims'

export const PROFILE_STORAGE_KEY = 'bevosita:profile'

/** Refresh this long before expiry so an in-flight call never races the clock. */
const REFRESH_MARGIN_MS = 60_000
const MIN_REFRESH_DELAY_MS = 5_000

export type AuthStatus = 'loading' | 'anonymous' | 'authenticated'

export interface ApiCall {
  token: string
  signal?: AbortSignal
}

export interface AuthApi {
  status: AuthStatus
  /** The signed-in user's display profile, when known. */
  user: UserSummary | null
  /** Authoritative for chrome; re-checked server-side on every request. */
  role: Role | null
  signIn: (email: string, password: string) => Promise<UserSummary>
  signOut: () => Promise<void>
  /**
   * Run an API call with the current access token, refreshing once and
   * replaying it if the token expired mid-session.
   */
  callApi: <T>(call: (auth: ApiCall) => Promise<T>, signal?: AbortSignal) => Promise<T>
}

const AuthContext = createContext<AuthApi | null>(null)

function readCachedProfile(): UserSummary | null {
  try {
    const raw = localStorage.getItem(PROFILE_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<UserSummary>
    if (typeof parsed?.id !== 'string' || (parsed.role !== 'founder' && parsed.role !== 'vc')) return null
    return parsed as UserSummary
  } catch {
    return null
  }
}

function writeCachedProfile(user: UserSummary | null): void {
  try {
    if (user) localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(user))
    else localStorage.removeItem(PROFILE_STORAGE_KEY)
  } catch {
    // Storage unavailable (private mode, quota): the session still works,
    // the chrome just shows no name until the next sign-in.
  }
}

export function AuthProvider({
  children,
  restoreSession = true,
}: {
  children: ReactNode
  /**
   * Ask the API to restore a session from the refresh cookie on mount.
   * Set to false for surfaces that must never contact the API at all (the
   * simulated demo); they start — and stay — anonymous until a real sign-in.
   */
  restoreSession?: boolean
}) {
  const [status, setStatus] = useState<AuthStatus>(restoreSession ? 'loading' : 'anonymous')
  const [user, setUser] = useState<UserSummary | null>(null)
  const [role, setRole] = useState<Role | null>(null)
  // Memory-only credential; state exists so consumers re-render, the ref so
  // callApi always reads the newest value without stale-closure surprises.
  const tokenRef = useRef<string | null>(null)
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inFlightRefresh = useRef<Promise<string | null> | null>(null)
  const mounted = useRef(true)

  const clearSession = useCallback(() => {
    tokenRef.current = null
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    refreshTimer.current = null
    writeCachedProfile(null)
    if (!mounted.current) return
    setUser(null)
    setRole(null)
    setStatus('anonymous')
  }, [])

  /** Adopt a freshly issued access token; `profile` is only known at sign-in. */
  const adoptToken = useCallback(
    (accessToken: string, profile?: UserSummary | null): Role | null => {
      const claims = readAccessClaims(accessToken)
      if (!claims) {
        clearSession()
        return null
      }
      tokenRef.current = accessToken
      // A cached profile is display data only: it must describe the very user
      // and role this token is for, or it is dropped rather than shown.
      const candidate = profile ?? readCachedProfile()
      const trusted = candidate && candidate.id === claims.userId && candidate.role === claims.role ? candidate : null
      writeCachedProfile(trusted)
      if (mounted.current) {
        setUser(trusted)
        setRole(claims.role)
        setStatus('authenticated')
      }
      return claims.role
    },
    [clearSession],
  )

  /** One shared refresh at a time: concurrent 401s must not stampede. */
  const refreshToken = useCallback(async (): Promise<string | null> => {
    if (inFlightRefresh.current) return inFlightRefresh.current
    const attempt = (async () => {
      try {
        const granted = await authApi.refresh()
        adoptToken(granted.access_token)
        return granted.access_token
      } catch {
        clearSession()
        return null
      } finally {
        inFlightRefresh.current = null
      }
    })()
    inFlightRefresh.current = attempt
    return attempt
  }, [adoptToken, clearSession])

  // Silent restore: the HttpOnly cookie is the only thing that survives a
  // reload, so the app always asks the server whether a session still exists.
  useEffect(() => {
    mounted.current = true
    if (restoreSession) void refreshToken()
    return () => {
      mounted.current = false
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
    }
  }, [refreshToken, restoreSession])

  // Keep the in-memory token fresh while the tab stays open.
  useEffect(() => {
    if (status !== 'authenticated' || !tokenRef.current) return
    const claims = readAccessClaims(tokenRef.current)
    if (!claims) return
    const delay = Math.max(claims.expiresAt - Date.now() - REFRESH_MARGIN_MS, MIN_REFRESH_DELAY_MS)
    refreshTimer.current = setTimeout(() => void refreshToken(), delay)
    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
    }
  }, [status, refreshToken])

  const signIn = useCallback(
    async (email: string, password: string): Promise<UserSummary> => {
      const granted = await authApi.login(email, password)
      adoptToken(granted.access_token, granted.user)
      return granted.user
    },
    [adoptToken],
  )

  const signOut = useCallback(async (): Promise<void> => {
    try {
      await authApi.logout()
    } catch {
      // Logout is idempotent server-side; a failed call must still end the
      // session in this tab rather than leave a half-signed-in UI.
    }
    clearSession()
  }, [clearSession])

  const callApi = useCallback(
    async <T,>(call: (auth: ApiCall) => Promise<T>, signal?: AbortSignal): Promise<T> => {
      const token = tokenRef.current ?? (await refreshToken())
      if (!token) throw new ApiError({ status: 401, code: 'AUTH_SESSION_REVOKED', messageKey: 'errors.sessionRevoked', detail: 'no session' })
      try {
        return await call({ token, signal })
      } catch (error) {
        if (!(error instanceof ApiError)) throw error
        if (error.code === 'AUTH_TOKEN_EXPIRED') {
          const renewed = await refreshToken()
          if (!renewed) throw error
          return call({ token: renewed, signal })
        }
        // The server has repudiated this session (revoked, deleted, or
        // role-drifted): stop pretending it is still signed in.
        if (error.code === 'AUTH_SESSION_REVOKED' || error.code === 'AUTH_TOKEN_INVALID') clearSession()
        throw error
      }
    },
    [refreshToken, clearSession],
  )

  const api = useMemo<AuthApi>(
    () => ({ status, user, role, signIn, signOut, callApi }),
    [status, user, role, signIn, signOut, callApi],
  )
  return <AuthContext.Provider value={api}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
