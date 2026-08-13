/**
 * The single seam between the browser app and the Bevosita API.
 *
 * Everything the UI knows about HTTP lives here: the base URL, the canonical
 * error envelope (backend/app/errors.py), bearer headers, and the deliberate
 * credentials policy.
 *
 * Credentials policy, mirroring the backend's cookie contract
 * (backend/app/security/cookies.py): the refresh token is an HttpOnly cookie
 * scoped to `/auth`, so ONLY the auth calls that rotate or revoke it opt into
 * `credentials: 'include'`. Every ordinary API call is `omit` — an ambient
 * cookie must never accompany a request that is authorized by a bearer token.
 */

/** The canonical error body every API failure carries. */
interface ErrorEnvelope {
  error: { code: string; message_key: string; detail: string; request_id: string }
}

export const NETWORK_ERROR_CODE = 'NETWORK_UNREACHABLE'

/** A failed API call: the canonical envelope, typed. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly messageKey: string
  readonly detail: string
  readonly requestId: string

  constructor(init: {
    status: number
    code: string
    messageKey: string
    detail: string
    requestId?: string
  }) {
    super(`${init.code} (${init.status})`)
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.messageKey = init.messageKey
    this.detail = init.detail
    this.requestId = init.requestId ?? ''
  }
}

function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== 'object' || body === null) return false
  const error = (body as { error?: unknown }).error
  return typeof error === 'object' && error !== null && typeof (error as { code?: unknown }).code === 'string'
}

/** Configured at build time; the local default matches backend/.env.example. */
export function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL as string | undefined
  return (configured && configured.trim() ? configured.trim() : 'http://localhost:8000').replace(/\/+$/, '')
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  /** Body serialized as JSON. Mutually exclusive with `form`. */
  json?: unknown
  /** Multipart body; the browser owns the Content-Type boundary. */
  form?: FormData
  /** Access token for bearer-authenticated routes. */
  token?: string | null
  /** Opt in to the HttpOnly refresh cookie — `/auth/refresh` and `/auth/logout` only. */
  withCredentials?: boolean
  signal?: AbortSignal
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/**
 * Perform one API call and return its parsed body.
 *
 * Failures — HTTP and transport alike — always leave as an `ApiError`, so no
 * caller has to distinguish "the server said no" from "the server is not
 * there"; the UI maps `code` to a localized message.
 */
export async function request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, form, token, withCredentials = false, signal } = options
  const headers = new Headers({ Accept: 'application/json' })
  if (token) headers.set('Authorization', `Bearer ${token}`)
  // Only for JSON: setting it on FormData would strip the multipart boundary.
  if (json !== undefined) headers.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method,
      headers,
      body: form ?? (json !== undefined ? JSON.stringify(json) : undefined),
      credentials: withCredentials ? 'include' : 'omit',
      signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError({
      status: 0,
      code: NETWORK_ERROR_CODE,
      messageKey: 'errors.networkUnreachable',
      detail: 'the api could not be reached',
    })
  }

  if (response.status === 204) return undefined as T

  const body = await parseJson(response)
  if (!response.ok) {
    if (isErrorEnvelope(body)) {
      throw new ApiError({
        status: response.status,
        code: body.error.code,
        messageKey: body.error.message_key,
        detail: body.error.detail,
        requestId: body.error.request_id,
      })
    }
    // A non-envelope failure (proxy, gateway, crash before the handlers):
    // never surface the raw body, which may not be ours at all.
    throw new ApiError({
      status: response.status,
      code: `HTTP_${response.status}`,
      messageKey: 'errors.serverError',
      detail: `request failed with status ${response.status}`,
    })
  }
  return body as T
}

/** Fetch binary content (the founder's own pitch deck) as a Blob. */
export async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const headers = new Headers()
  if (options.token) headers.set('Authorization', `Bearer ${options.token}`)
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: options.method ?? 'GET',
      headers,
      credentials: 'omit',
      signal: options.signal,
    })
  } catch {
    throw new ApiError({
      status: 0,
      code: NETWORK_ERROR_CODE,
      messageKey: 'errors.networkUnreachable',
      detail: 'the api could not be reached',
    })
  }
  if (!response.ok) {
    const body = await parseJson(response)
    if (isErrorEnvelope(body)) {
      throw new ApiError({
        status: response.status,
        code: body.error.code,
        messageKey: body.error.message_key,
        detail: body.error.detail,
        requestId: body.error.request_id,
      })
    }
    throw new ApiError({
      status: response.status,
      code: `HTTP_${response.status}`,
      messageKey: 'errors.serverError',
      detail: `request failed with status ${response.status}`,
    })
  }
  return response.blob()
}
