import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NETWORK_ERROR_CODE, apiBaseUrl, request } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** The ApiError a rejected call produced, typed for assertions. */
async function captureError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
    throw new Error('expected the request to reject')
  } catch (error) {
    return error as ApiError
  }
}

const errorEnvelope = (code: string, detail = 'nope') => ({
  error: { code, message_key: `errors.${code}`, detail, request_id: 'req-1' },
})

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

describe('apiBaseUrl', () => {
  it('has no trailing slash so paths concatenate exactly once', () => {
    expect(apiBaseUrl().endsWith('/')).toBe(false)
    expect(apiBaseUrl()).toMatch(/^https?:\/\//)
  })
})

describe('request', () => {
  it('sends JSON with the bearer token and returns the parsed body', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { id: 's1', name: 'Xarid' }))

    const result = await request<{ id: string; name: string }>('/founder/startups/s1', {
      token: 'tok-123',
    })

    expect(result).toEqual({ id: 's1', name: 'Xarid' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${apiBaseUrl()}/founder/startups/s1`)
    expect(init.method).toBe('GET')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok-123')
    // A bearer-authenticated read must not drag the refresh cookie along.
    expect(init.credentials).toBe('omit')
  })

  it('serializes a JSON body and never sets Authorization without a token', async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { ok: true }))

    await request('/auth/login', { method: 'POST', json: { email: 'a@b.uz' } })

    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBe('{"email":"a@b.uz"}')
    const headers = new Headers(init.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.has('Authorization')).toBe(false)
  })

  it('sends the refresh cookie only when a call explicitly opts in', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { access_token: 't' }))

    await request('/auth/refresh', { method: 'POST', withCredentials: true })

    expect(fetchMock.mock.calls[0][1].credentials).toBe('include')
  })

  it('returns undefined for a 204 without trying to parse a body', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    await expect(request('/auth/logout', { method: 'POST' })).resolves.toBeUndefined()
  })

  it('throws a typed ApiError carrying the canonical envelope', async () => {
    fetchMock.mockResolvedValue(jsonResponse(409, errorEnvelope('STARTUP_LOCKED', 'locked')))

    const error = await captureError(request('/founder/startups/s1', { method: 'PATCH', json: {} }))

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(409)
    expect(error.code).toBe('STARTUP_LOCKED')
    expect(error.messageKey).toBe('errors.STARTUP_LOCKED')
    expect(error.detail).toBe('locked')
    expect(error.requestId).toBe('req-1')
  })

  it('falls back to a status-derived error when the body is not an envelope', async () => {
    fetchMock.mockResolvedValue(new Response('<html>gateway</html>', { status: 502 }))

    const error = await captureError(request('/founder/startups'))

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.code).toBe('HTTP_502')
    // Never echo an unparsed body back into the UI.
    expect(error.detail).not.toContain('<html>')
  })

  it('reports an unreachable API as a network error rather than a crash', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const error = await captureError(request('/founder/startups'))

    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe(NETWORK_ERROR_CODE)
    expect(error.status).toBe(0)
  })

  it('passes FormData through untouched so the browser sets the multipart boundary', async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { id: 'd1' }))
    const form = new FormData()
    form.append('file', new Blob(['%PDF-1.4']), 'deck.pdf')

    await request('/founder/startups/s1/deck', { method: 'PUT', form, token: 't' })

    const [, init] = fetchMock.mock.calls[0]
    expect(init.body).toBe(form)
    expect(new Headers(init.headers).has('Content-Type')).toBe(false)
  })

  it('surfaces the abort signal so a stale request can be cancelled', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}))
    const controller = new AbortController()

    await request('/founder/startups', { signal: controller.signal })

    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })
})
