import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApiError } from '../api/client'
import { AuthProvider, PROFILE_STORAGE_KEY, useAuth } from './session'
import { makeAccessToken, makeUser } from '../test/factories'

let fetchMock: ReturnType<typeof vi.fn>

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const revoked = () =>
  json(401, {
    error: { code: 'AUTH_SESSION_REVOKED', message_key: 'errors.sessionRevoked', detail: 'nope', request_id: 'r' },
  })

const expiredToken = () =>
  json(401, {
    error: { code: 'AUTH_TOKEN_EXPIRED', message_key: 'errors.tokenExpired', detail: 'nope', request_id: 'r' },
  })

/** Prints the session state so assertions read like the UI would see it. */
function Probe() {
  const { status, user, role } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="role">{role ?? '-'}</span>
      <span data-testid="name">{user?.full_name ?? '-'}</span>
    </div>
  )
}

function renderProbe(children = <Probe />) {
  return render(<AuthProvider>{children}</AuthProvider>)
}

beforeEach(() => {
  localStorage.clear()
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

describe('silent session restore', () => {
  it('asks the refresh cookie for a session on mount and settles anonymous when there is none', async () => {
    fetchMock.mockResolvedValue(revoked())
    renderProbe()

    expect(screen.getByTestId('status')).toHaveTextContent('loading')
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/auth\/refresh$/)
    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
  })

  it('restores the role from the access token itself, not from storage', async () => {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(makeUser({ id: 'user-1', role: 'founder' })))
    fetchMock.mockResolvedValue(
      json(200, { access_token: makeAccessToken({ sub: 'user-1', role: 'founder' }), token_type: 'bearer', expires_in: 900 }),
    )

    renderProbe()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('role')).toHaveTextContent('founder')
    expect(screen.getByTestId('name')).toHaveTextContent('Aziza Karimova')
  })

  it('ignores a cached profile that does not match the token it arrived with', async () => {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(makeUser({ id: 'someone-else', role: 'vc' })))
    fetchMock.mockResolvedValue(
      json(200, { access_token: makeAccessToken({ sub: 'user-1', role: 'founder' }), token_type: 'bearer', expires_in: 900 }),
    )

    renderProbe()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('role')).toHaveTextContent('founder')
    expect(screen.getByTestId('name')).toHaveTextContent('-')
  })

  it('stays anonymous when the API is unreachable instead of hanging on loading', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    renderProbe()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
  })
})

describe('sign in and out', () => {
  function LoginProbe() {
    const { status, signIn, signOut, role } = useAuth()
    return (
      <div>
        <span data-testid="status">{status}</span>
        <span data-testid="role">{role ?? '-'}</span>
        <button type="button" onClick={() => void signIn('aziza@bevosita.test', 'correct-horse')}>
          in
        </button>
        <button type="button" onClick={() => void signOut()}>
          out
        </button>
      </div>
    )
  }

  it('keeps the access token out of every web storage', async () => {
    const user = userEvent.setup()
    const token = makeAccessToken({ sub: 'user-1', role: 'founder' })
    fetchMock.mockResolvedValueOnce(revoked())
    fetchMock.mockResolvedValueOnce(json(200, { access_token: token, token_type: 'bearer', expires_in: 900, user: makeUser() }))

    renderProbe(<LoginProbe />)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    await user.click(screen.getByRole('button', { name: 'in' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    const stored = JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } })
    expect(stored).not.toContain(token)
    // Only the non-secret display profile is cached, for chrome after reload.
    expect(JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY)!).email).toBe('aziza@bevosita.test')
  })

  it('revokes the session server-side and drops the cached profile on sign out', async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValueOnce(
      json(200, { access_token: makeAccessToken(), token_type: 'bearer', expires_in: 900 }),
    )
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

    renderProbe(<LoginProbe />)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    await user.click(screen.getByRole('button', { name: 'out' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    const logoutCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/auth/logout'))!
    expect(logoutCall[1].credentials).toBe('include')
    expect(localStorage.getItem(PROFILE_STORAGE_KEY)).toBeNull()
  })

  it('surfaces the API error instead of pretending the login worked', async () => {
    const user = userEvent.setup()
    function FailingProbe() {
      const { signIn } = useAuth()
      return (
        <button
          type="button"
          onClick={() => void signIn('a@b.uz', 'wrong').catch((error: ApiError) => {
            document.title = error.code
          })}
        >
          in
        </button>
      )
    }
    fetchMock.mockResolvedValueOnce(revoked())
    fetchMock.mockResolvedValueOnce(
      json(401, { error: { code: 'AUTH_INVALID_CREDENTIALS', message_key: 'errors.invalidCredentials', detail: 'no', request_id: 'r' } }),
    )

    renderProbe(<FailingProbe />)
    await user.click(screen.getByRole('button', { name: 'in' }))

    await waitFor(() => expect(document.title).toBe('AUTH_INVALID_CREDENTIALS'))
  })
})

describe('callApi', () => {
  function CallProbe() {
    const { status, callApi } = useAuth()
    return (
      <div>
        <span data-testid="status">{status}</span>
        <button
          type="button"
          onClick={() =>
            void callApi<{ ok: boolean }>(({ token }) =>
              fetch('http://api.test/founder/startups', { headers: { Authorization: `Bearer ${token}` } }).then(
                async (response) => {
                  if (!response.ok) {
                    const body = await response.json()
                    throw new ApiError({
                      status: response.status,
                      code: body.error.code,
                      messageKey: body.error.message_key,
                      detail: body.error.detail,
                    })
                  }
                  return response.json()
                },
              ),
            )
              .then((value) => {
                document.title = JSON.stringify(value)
              })
              .catch((error: ApiError) => {
                document.title = `failed:${error.code}`
              })
          }
        >
          load
        </button>
      </div>
    )
  }

  it('refreshes once and replays the call when the access token has expired', async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(json(200, { access_token: makeAccessToken(), token_type: 'bearer', expires_in: 900 }))
      .mockResolvedValueOnce(expiredToken())
      .mockResolvedValueOnce(json(200, { access_token: makeAccessToken(), token_type: 'bearer', expires_in: 900 }))
      .mockResolvedValueOnce(json(200, { ok: true }))

    renderProbe(<CallProbe />)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    await user.click(screen.getByRole('button', { name: 'load' }))

    await waitFor(() => expect(document.title).toBe('{"ok":true}'))
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'))).toHaveLength(2)
  })

  it('signs the user out when the refresh behind a retry also fails', async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(json(200, { access_token: makeAccessToken(), token_type: 'bearer', expires_in: 900 }))
      .mockResolvedValueOnce(expiredToken())
      .mockResolvedValueOnce(revoked())

    renderProbe(<CallProbe />)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    await user.click(screen.getByRole('button', { name: 'load' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    expect(document.title).toBe('failed:AUTH_TOKEN_EXPIRED')
  })

  it('signs the user out when the server says the session was revoked', async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(json(200, { access_token: makeAccessToken(), token_type: 'bearer', expires_in: 900 }))
      .mockResolvedValueOnce(revoked())

    renderProbe(<CallProbe />)
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    await user.click(screen.getByRole('button', { name: 'load' }))

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
  })
})
