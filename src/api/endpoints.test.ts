import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as authApi from './auth'
import * as founderApi from './founder'
import * as vcApi from './vc'
import { apiBaseUrl } from './client'

let fetchMock: ReturnType<typeof vi.fn>

function ok(body: unknown = {}) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

/** [url, method, credentials] of the single call the wrapper made. */
function callShape(): [string, string, string] {
  const [url, init] = fetchMock.mock.calls[0]
  return [String(url).replace(apiBaseUrl(), ''), init.method, init.credentials]
}

beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(ok())
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => vi.unstubAllGlobals())

const call = { token: 'tok' }

describe('auth endpoints', () => {
  it('posts credentials to /auth/login and keeps the cookie the server sets', async () => {
    await authApi.login('a@b.uz', 'secret-password')
    // `omit` would make the browser discard the response's Set-Cookie, so the
    // session could never survive a reload.
    expect(callShape()).toEqual(['/auth/login', 'POST', 'include'])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'a@b.uz', password: 'secret-password' })
  })

  it.each([
    ['refresh', () => authApi.refresh(), '/auth/refresh'],
    ['logout', () => authApi.logout(), '/auth/logout'],
  ])('sends the refresh cookie for %s', async (_name, invoke, path) => {
    await invoke()
    expect(callShape()).toEqual([path, 'POST', 'include'])
  })

  it.each([
    ['activate-invite', () => authApi.activateInvite({ token: 't', email: 'a@b.uz', password: 'p'.repeat(10), full_name: 'A B', locale: 'uz' }), '/auth/activate-invite'],
    ['verify-email', () => authApi.verifyEmail('t'), '/auth/verify-email'],
    ['forgot-password', () => authApi.forgotPassword('a@b.uz'), '/auth/forgot-password'],
    ['reset-password', () => authApi.resetPassword('t', 'p'.repeat(10)), '/auth/reset-password'],
  ])('posts %s as a cookieless public call', async (_name, invoke, path) => {
    await invoke()
    expect(callShape()).toEqual([path, 'POST', 'omit'])
  })
})

describe('founder endpoints', () => {
  it.each([
    ['list', () => founderApi.listStartups(call), '/founder/startups', 'GET'],
    ['create', () => founderApi.createStartup({ name: 'Xarid' }, call), '/founder/startups', 'POST'],
    ['detail', () => founderApi.getStartup('s1', call), '/founder/startups/s1', 'GET'],
    ['patch metadata', () => founderApi.patchStartup('s1', { city: 'Toshkent' }, call), '/founder/startups/s1', 'PATCH'],
    ['patch submission', () => founderApi.patchSubmission('s1', { problem: 'x' }, call), '/founder/startups/s1/submission', 'PATCH'],
    ['submit', () => founderApi.submitStartup('s1', call), '/founder/startups/s1/submit', 'POST'],
    ['deck metadata', () => founderApi.getDeckMetadata('s1', call), '/founder/startups/s1/deck/metadata', 'GET'],
    ['delete deck', () => founderApi.deleteDeck('s1', call), '/founder/startups/s1/deck', 'DELETE'],
    ['payment', () => founderApi.getPayment('s1', call), '/founder/startups/s1/payment', 'GET'],
    ['pay', () => founderApi.submitPayment('s1', 'paid', call), '/founder/startups/s1/payment', 'POST'],
    ['consents', () => founderApi.getConsents('s1', call), '/founder/startups/s1/consents', 'GET'],
    ['grant consent', () => founderApi.grantConsent('s1', 'ai-privacy.v1', call), '/founder/startups/s1/consents', 'POST'],
    ['analysis status', () => founderApi.getAnalysis('s1', call), '/founder/startups/s1/analysis', 'GET'],
    ['trigger analysis', () => founderApi.triggerAnalysis('s1', call), '/founder/startups/s1/analysis', 'POST'],
    ['report', () => founderApi.getReport('s1', call), '/founder/startups/s1/report', 'GET'],
    ['narrative', () => founderApi.getNarrative('s1', call), '/founder/startups/s1/narrative', 'GET'],
    ['save narrative', () => founderApi.saveNarrative('s1', 'text', call), '/founder/startups/s1/narrative', 'PATCH'],
    ['versions', () => founderApi.listNarrativeVersions('s1', call), '/founder/startups/s1/narrative/versions', 'GET'],
    ['one version', () => founderApi.getNarrativeVersion('s1', 3, call), '/founder/startups/s1/narrative/versions/3', 'GET'],
    ['approval', () => founderApi.getApproval('s1', call), '/founder/startups/s1/narrative/approval', 'GET'],
    ['approve', () => founderApi.approveNarrative('s1', 2, call), '/founder/startups/s1/narrative/approval', 'POST'],
  ])('routes %s to the documented endpoint with a bearer token and no cookie', async (_name, invoke, path, method) => {
    await invoke()
    expect(callShape()).toEqual([path, method, 'omit'])
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('Authorization')).toBe('Bearer tok')
  })

  it('uploads a deck as multipart form data under the `file` field', async () => {
    const file = new File(['%PDF-1.4'], 'deck.pdf', { type: 'application/pdf' })
    await founderApi.uploadDeck('s1', file, call)

    expect(callShape()).toEqual(['/founder/startups/s1/deck', 'PUT', 'omit'])
    const body = fetchMock.mock.calls[0][1].body as FormData
    expect(body.get('file')).toBeInstanceOf(File)
    expect((body.get('file') as File).name).toBe('deck.pdf')
  })

  it('approves an explicit version number, never "whatever is current"', async () => {
    await founderApi.approveNarrative('s1', 4, call)
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ version: 4 })
  })
})

describe('vc endpoints', () => {
  it('requests a bounded page of approved startups', async () => {
    await vcApi.listApprovedStartups(call, { limit: 5, offset: 10 })
    expect(callShape()).toEqual(['/vc/startups?limit=5&offset=10', 'GET', 'omit'])
  })

  it('defaults to the documented page size', async () => {
    await vcApi.listApprovedStartups(call)
    expect(callShape()[0]).toBe(`/vc/startups?limit=${vcApi.VC_PAGE_SIZE}&offset=0`)
  })

  it('opens one dossier by id', async () => {
    await vcApi.getDossier('s9', call)
    expect(callShape()).toEqual(['/vc/startups/s9', 'GET', 'omit'])
  })
})
