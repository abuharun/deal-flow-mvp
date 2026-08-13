/**
 * A fake backend for tests that drive the real app through the real router.
 *
 * The fake answers ONLY the endpoints a test explicitly registered: any other
 * call throws, so a component that starts talking to an endpoint nobody
 * declared fails loudly instead of silently rendering an error state. Bodies
 * are built from `src/test/factories.ts`, which mirrors the FastAPI schemas.
 */

import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AppRoutes } from '../App'
import { AuthProvider } from '../auth/session'
import { StoreProvider } from '../lib/store'
import { ToastProvider } from '../components/toast'
import { LocaleProvider, type Locale } from '../i18n'
import { makeAccessToken, makeUser } from './factories'

export type Handler = (init: RequestInit) => Response | Promise<Response>

let routes: Map<string, Handler>
let calls: string[]

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** The canonical error envelope from backend/app/errors.py. */
export function envelope(code: string, status: number): Response {
  return json({ error: { code, message_key: `errors.${code}`, detail: 'no', request_id: 'req-7' } }, status)
}

/** Register `METHOD /path` (path only, query stripped). */
export function route(key: string, handler: Handler) {
  routes.set(key, handler)
}

/** Every `METHOD /path` the app has called, in order. */
export function apiCalls(): string[] {
  return calls
}

/** The parsed JSON body of the nth call to `key`, or the last one by default. */
export function bodyOf(key: string, index = -1): unknown {
  const mock = (globalThis.fetch as unknown as { mock: { calls: [URL | string, RequestInit][] } }).mock
  const matching = mock.calls.filter(([input, init]) => `${init.method ?? 'GET'} ${new URL(String(input)).pathname}` === key)
  const entry = matching.at(index)
  if (!entry) throw new Error(`no call recorded for ${key}`)
  const body = entry[1].body
  return typeof body === 'string' ? JSON.parse(body) : body
}

export function installFakeApi() {
  routes = new Map()
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = new URL(String(input))
      const key = `${init.method ?? 'GET'} ${url.pathname}`
      calls.push(key)
      const handler = routes.get(key)
      if (!handler) throw new Error(`unexpected API call: ${key}`)
      return handler(init)
    }),
  )
}

/** Sign-in plus a session the refresh cookie can restore. */
export function grantSession(role: 'founder' | 'vc') {
  const token = makeAccessToken({ sub: 'user-1', role })
  route('POST /auth/refresh', () => json({ access_token: token, token_type: 'bearer', expires_in: 900 }))
  route('POST /auth/login', () =>
    json({ access_token: token, token_type: 'bearer', expires_in: 900, user: makeUser({ role }) }),
  )
  return token
}

export function renderApp(path: string, locale: Locale = 'uz') {
  return render(
    <LocaleProvider initial={locale}>
      <AuthProvider>
        <StoreProvider>
          <ToastProvider>
            <MemoryRouter initialEntries={[path]}>
              <AppRoutes />
            </MemoryRouter>
          </ToastProvider>
        </StoreProvider>
      </AuthProvider>
    </LocaleProvider>,
  )
}
