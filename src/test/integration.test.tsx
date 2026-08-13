/**
 * End-to-end-through-the-router tests: the real `AppRoutes`, mounted with the
 * real `AuthProvider` and the real API modules, against a stubbed HTTP layer.
 *
 * These prove the product routes are wired to the backend rather than to the
 * simulated store: every assertion below is reachable only if the app actually
 * called the documented endpoint and rendered what that endpoint returned.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { AuthProvider } from '../auth/session'
import { StoreProvider } from '../lib/store'
import { ToastProvider } from '../components/toast'
import { LocaleProvider, type Locale } from '../i18n'
import {
  makeAccessToken,
  makeAnalysisJob,
  makeApproval,
  makeConsents,
  makeDeck,
  makeDossier,
  makeNarrative,
  makePayment,
  makeStartup,
  makeStartupDetail,
  makeUser,
  makeVcSummary,
} from './factories'

type Handler = (init: RequestInit) => Response | Promise<Response>

let routes: Map<string, Handler>
let calls: string[]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function envelope(code: string, status: number): Response {
  return json({ error: { code, message_key: `errors.${code}`, detail: 'no', request_id: 'req-7' } }, status)
}

/** Register `METHOD /path` (path only, query stripped). */
function route(key: string, handler: Handler) {
  routes.set(key, handler)
}

/** A fake backend that answers ONLY the endpoints it was told about. */
function installFakeApi() {
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
function grantSession(role: 'founder' | 'vc') {
  const token = makeAccessToken({ sub: 'user-1', role })
  route('POST /auth/refresh', () => json({ access_token: token, token_type: 'bearer', expires_in: 900 }))
  route('POST /auth/login', () =>
    json({ access_token: token, token_type: 'bearer', expires_in: 900, user: makeUser({ role }) }),
  )
  return token
}

function renderApp(path: string, locale: Locale = 'uz') {
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

beforeEach(() => {
  localStorage.clear()
  installFakeApi()
})

afterEach(() => vi.unstubAllGlobals())

describe('real authentication at /login', () => {
  it('signs in against POST /auth/login and lands a founder in the API-backed workspace', async () => {
    const user = userEvent.setup()
    // No cookie session yet: the app must actually sign in to get anywhere.
    grantSession('founder')
    route('POST /auth/refresh', () => envelope('AUTH_SESSION_REVOKED', 401))
    route('GET /founder/startups', () => json([makeStartup({ name: 'Xarid' })]))

    renderApp('/login')

    await user.type(await screen.findByLabelText('Email'), 'aziza@bevosita.test')
    await user.type(screen.getByLabelText('Parol'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Kirish' }))

    // The startup name can only appear if the app called the real endpoint.
    expect(await screen.findByRole('heading', { name: 'Xarid' })).toBeInTheDocument()
    expect(calls).toContain('POST /auth/login')
    expect(calls).toContain('GET /founder/startups')
    // No seeded demo startup leaked into the real workspace.
    expect(screen.queryByText(/SolarUz/)).not.toBeInTheDocument()
  })

  it('shows the API’s own reason for a rejected sign-in', async () => {
    const user = userEvent.setup()
    route('POST /auth/refresh', () => envelope('AUTH_SESSION_REVOKED', 401))
    route('POST /auth/login', () => envelope('AUTH_INVALID_CREDENTIALS', 401))

    renderApp('/login')

    await user.type(await screen.findByLabelText('Email'), 'aziza@bevosita.test')
    await user.type(screen.getByLabelText('Parol'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Kirish' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Email yoki parol noto‘g‘ri.')
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
  })

  it('keeps an unverified account out with the backend’s specific message', async () => {
    const user = userEvent.setup()
    route('POST /auth/refresh', () => envelope('AUTH_SESSION_REVOKED', 401))
    route('POST /auth/login', () => envelope('AUTH_EMAIL_UNVERIFIED', 401))

    renderApp('/login')
    await user.type(await screen.findByLabelText('Email'), 'aziza@bevosita.test')
    await user.type(screen.getByLabelText('Parol'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Kirish' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/tasdiqlanmagan/)
  })
})

describe('session-based route protection', () => {
  it('sends an anonymous visitor from /founder to the real login page', async () => {
    route('POST /auth/refresh', () => envelope('AUTH_SESSION_REVOKED', 401))

    renderApp('/founder')

    expect(await screen.findByRole('heading', { name: 'Kirish' })).toBeInTheDocument()
    expect(calls).toEqual(['POST /auth/refresh'])
  })

  it('restores a session from the refresh cookie without any stored token', async () => {
    grantSession('founder')
    route('GET /founder/startups', () => json([makeStartup({ name: 'Xarid' })]))

    renderApp('/founder')

    expect(await screen.findByRole('heading', { name: 'Xarid' })).toBeInTheDocument()
    expect(calls[0]).toBe('POST /auth/refresh')
    expect(JSON.stringify({ ...localStorage })).not.toContain('eyJ')
  })

  it('routes a VC away from the founder workspace and into their own', async () => {
    grantSession('vc')
    route('GET /vc/startups', () => json({ items: [], limit: 20, offset: 0, total: 0 }))

    renderApp('/founder')

    expect(await screen.findByRole('heading', { name: 'Tasdiqlangan startaplar' })).toBeInTheDocument()
    expect(calls).not.toContain('GET /founder/startups')
  })

  it('routes a founder away from the investor workspace', async () => {
    grantSession('founder')
    route('GET /founder/startups', () => json([]))

    renderApp('/investor')

    expect(await screen.findByRole('heading', { name: 'Startaplarim' })).toBeInTheDocument()
    expect(calls).not.toContain('GET /vc/startups')
  })

  it('signs out through POST /auth/logout and returns to the public landing', async () => {
    const user = userEvent.setup()
    grantSession('founder')
    route('GET /founder/startups', () => json([]))
    route('POST /auth/logout', () => new Response(null, { status: 204 }))

    renderApp('/founder')
    await screen.findByRole('heading', { name: 'Startaplarim' })
    await user.click(screen.getByRole('button', { name: 'Chiqish' }))

    await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/halol xulosa/))
    await waitFor(() => expect(calls).toContain('POST /auth/logout'))
  })
})

describe('founder workspace against the real API', () => {
  it('reports an empty account honestly instead of inventing a startup', async () => {
    grantSession('founder')
    route('GET /founder/startups', () => json([]))

    renderApp('/founder')

    expect(await screen.findByRole('heading', { name: 'Hali startap qo‘shilmagan' })).toBeInTheDocument()
  })

  it('surfaces a server failure with a retry that calls the endpoint again', async () => {
    const user = userEvent.setup()
    grantSession('founder')
    let attempts = 0
    route('GET /founder/startups', () => {
      attempts += 1
      return attempts === 1 ? envelope('SERVER_ERROR', 500) : json([makeStartup({ name: 'Xarid' })])
    })

    renderApp('/founder')

    expect(await screen.findByRole('alert')).toHaveTextContent(/kutilmagan xatolik/)
    await user.click(screen.getByRole('button', { name: 'Qayta urinish' }))

    expect(await screen.findByRole('heading', { name: 'Xarid' })).toBeInTheDocument()
    expect(attempts).toBe(2)
  })

  it('builds one startup’s progress out of the seven real resources', async () => {
    grantSession('founder')
    route('GET /founder/startups/startup-1', () =>
      json(
        makeStartupDetail({
          status: 'report_ready',
          submitted_at: '2026-07-21T09:00:00Z',
          submission: { problem: 'Restoranlar', product: 'Marketpleys', market: 'B2B', traction: '240', team: '6', ask: '$500k' },
        }),
      ),
    )
    route('GET /founder/startups/startup-1/deck/metadata', () => json(makeDeck()))
    route('GET /founder/startups/startup-1/payment', () => json(makePayment()))
    route('GET /founder/startups/startup-1/consents', () => json(makeConsents()))
    route('GET /founder/startups/startup-1/analysis', () => json(makeAnalysisJob({ status: 'completed' })))
    route('GET /founder/startups/startup-1/narrative', () => json(makeNarrative()))
    route('GET /founder/startups/startup-1/narrative/approval', () => envelope('NARRATIVE_NOT_APPROVED', 404))

    renderApp('/founder/startup-1')

    const rail = await screen.findByRole('list', { name: 'Ariza bosqichlari' })
    const steps = within(rail).getAllByRole('listitem')
    expect(steps).toHaveLength(7)
    // Six backend facts done, approval is what the founder must do next.
    expect(steps.filter((step) => within(step).queryByText('Bajarildi'))).toHaveLength(6)
    expect(within(steps[6]).getByText('Navbatda')).toBeInTheDocument()
    expect(screen.getByText('xarid-deck.pdf')).toBeInTheDocument()
    expect(screen.getByText(/To‘langan \(demo\)/)).toBeInTheDocument()
  })

  it('reports each missing prerequisite as absent rather than filling it in', async () => {
    grantSession('founder')
    route('GET /founder/startups/startup-1', () => json(makeStartupDetail()))
    route('GET /founder/startups/startup-1/deck/metadata', () => envelope('DECK_NOT_FOUND', 404))
    route('GET /founder/startups/startup-1/payment', () => envelope('PAYMENT_NOT_FOUND', 404))
    route('GET /founder/startups/startup-1/consents', () => json(makeConsents({ granted: false, history: [] })))
    route('GET /founder/startups/startup-1/analysis', () => envelope('ANALYSIS_NOT_FOUND', 404))
    route('GET /founder/startups/startup-1/narrative', () => envelope('NARRATIVE_NOT_READY', 409))
    route('GET /founder/startups/startup-1/narrative/approval', () => envelope('NARRATIVE_NOT_APPROVED', 404))

    renderApp('/founder/startup-1')

    expect(await screen.findByText('Taqdimot hali yuklanmagan.')).toBeInTheDocument()
    expect(screen.getByText('To‘lov hali qayd etilmagan.')).toBeInTheDocument()
    expect(screen.getByText('Tadqiqot hali boshlanmagan.')).toBeInTheDocument()
    expect(screen.getByText('Matn hisobot tayyor bo‘lgach ochiladi.')).toBeInTheDocument()
    // Not-yet-wired mutations are labelled, never rendered as working controls.
    expect(screen.queryByRole('button', { name: 'Yuklash' })).not.toBeInTheDocument()
  })

  it('shows an approved startup as locked, with no editing offered', async () => {
    grantSession('founder')
    route('GET /founder/startups/startup-1', () =>
      json(
        makeStartupDetail({
          status: 'vc_visible',
          submitted_at: '2026-07-21T09:00:00Z',
          vc_visible_at: '2026-07-23T09:00:00Z',
        }),
      ),
    )
    route('GET /founder/startups/startup-1/deck/metadata', () => json(makeDeck()))
    route('GET /founder/startups/startup-1/payment', () => json(makePayment()))
    route('GET /founder/startups/startup-1/consents', () => json(makeConsents()))
    route('GET /founder/startups/startup-1/analysis', () => json(makeAnalysisJob({ status: 'completed' })))
    route('GET /founder/startups/startup-1/narrative', () => json(makeNarrative({ version: 2, source: 'founder_edit' })))
    route('GET /founder/startups/startup-1/narrative/approval', () => json(makeApproval()))

    renderApp('/founder/startup-1')

    expect(await screen.findByText('Ariza qulflangan')).toBeInTheDocument()
    expect(screen.getByText('Tasdiqlangan versiya: 2')).toBeInTheDocument()
  })

  it('answers a foreign or unknown startup id with the API’s canonical message', async () => {
    grantSession('founder')
    for (const path of [
      'GET /founder/startups/ghost',
      'GET /founder/startups/ghost/deck/metadata',
      'GET /founder/startups/ghost/payment',
      'GET /founder/startups/ghost/consents',
      'GET /founder/startups/ghost/analysis',
      'GET /founder/startups/ghost/narrative',
      'GET /founder/startups/ghost/narrative/approval',
    ]) {
      route(path, () => envelope('STARTUP_NOT_FOUND', 404))
    }

    renderApp('/founder/ghost')

    expect(await screen.findByRole('alert')).toHaveTextContent('Startap topilmadi.')
  })
})

describe('investor workspace against the real API', () => {
  it('lists only what GET /vc/startups returned', async () => {
    grantSession('vc')
    route('GET /vc/startups', () =>
      json({ items: [makeVcSummary({ name: 'Xarid' })], limit: 20, offset: 0, total: 1 }),
    )

    renderApp('/investor')

    expect(await screen.findByRole('heading', { name: 'Xarid' })).toBeInTheDocument()
    expect(screen.getByText('Jami: 1')).toBeInTheDocument()
  })

  it('says so plainly when no founder has approved anything yet', async () => {
    grantSession('vc')
    route('GET /vc/startups', () => json({ items: [], limit: 20, offset: 0, total: 0 }))

    renderApp('/investor')

    expect(await screen.findByRole('heading', { name: 'Hozircha tasdiqlangan startap yo‘q' })).toBeInTheDocument()
  })

  it('opens a frozen dossier with the approved narrative and its cited report', async () => {
    const user = userEvent.setup()
    grantSession('vc')
    route('GET /vc/startups', () =>
      json({ items: [makeVcSummary({ name: 'Xarid' })], limit: 20, offset: 0, total: 1 }),
    )
    route('GET /vc/startups/startup-1', () => json(makeDossier()))

    renderApp('/investor')
    await user.click(await screen.findByRole('heading', { name: 'Xarid' }))

    expect(await screen.findByRole('heading', { name: 'Asoschi tasdiqlagan matn' })).toBeInTheDocument()
    expect(screen.getByText(/verified weekly/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tadqiqot hisoboti' })).toBeInTheDocument()
    // Citations resolve to the report's own numbered sources.
    expect(screen.getByRole('link', { name: 'Uzbekistan food service statistics' })).toHaveAttribute(
      'href',
      'https://stat.uz/en/food-service',
    )
    // The dossier is read-only: no control on the page can change anything.
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Saqlash|Tasdiqlash/ })).not.toBeInTheDocument()
  })

  it('renders the whole investor surface in Russian when the locale is RU', async () => {
    grantSession('vc')
    route('GET /vc/startups', () =>
      json({ items: [makeVcSummary({ name: 'Xarid' })], limit: 20, offset: 0, total: 1 }),
    )

    renderApp('/investor', 'ru')

    expect(await screen.findByRole('heading', { name: 'Одобренные стартапы' })).toBeInTheDocument()
    expect(await screen.findByText('Всего: 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Обновить' })).toBeInTheDocument()
  })

  it('does not expose the founder-only report draft field to an investor', async () => {
    grantSession('vc')
    route('GET /vc/startups/startup-1', () => json(makeDossier()))

    renderApp('/investor/startup-1')

    await screen.findByRole('heading', { name: 'Tadqiqot hisoboti' })
    // `pitch_narrative_draft` is dropped by the API projection; nothing in the
    // dossier may reintroduce it.
    expect(document.body.textContent).not.toContain('connects restaurants to vetted suppliers.')
  })
})

describe('the simulated demo stays separate', () => {
  it('never calls the API from the /demo surface', async () => {
    const user = userEvent.setup()
    route('POST /auth/refresh', () => envelope('AUTH_SESSION_REVOKED', 401))

    renderApp('/demo')
    await user.click(await screen.findByRole('button', { name: /Asoschi/ }))
    await screen.findByRole('heading', { name: /investitsiyaga loyiqmi/ })

    await waitFor(() => expect(calls).toEqual(['POST /auth/refresh']))
  })
})
