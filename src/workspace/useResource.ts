/**
 * One API-backed resource with explicit loading / ready / error states.
 *
 * There is deliberately no fourth "empty because we guessed" state: a loader
 * that treats an expected 404 as absence must say so itself (see `optional`),
 * so the UI never invents data the API did not return.
 */

import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'

export type ResourceState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; error: ApiError }

export interface Resource<T> {
  state: ResourceState<T>
  /** Re-run the loader (after a mutation, or a failed attempt). */
  reload: () => void
  /** Adopt a value a mutation just returned, without a second round-trip. */
  replace: (data: T) => void
}

/**
 * `loader` must be referentially stable (wrap it in `useCallback`): it is the
 * effect's dependency, so an inline lambda would reload on every render.
 */
export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>): Resource<T> {
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setState({ status: 'loading' })
    loader(controller.signal)
      .then((data) => {
        if (active) setState({ status: 'ready', data })
      })
      .catch((error: unknown) => {
        // An aborted request is this component unmounting or reloading — not
        // a failure the user should ever see.
        if (!active || controller.signal.aborted) return
        setState({
          status: 'error',
          error:
            error instanceof ApiError
              ? error
              : new ApiError({ status: 0, code: 'SERVER_ERROR', messageKey: 'errors.serverError', detail: 'unexpected' }),
        })
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [loader, attempt])

  const reload = useCallback(() => setAttempt((value) => value + 1), [])
  const replace = useCallback((data: T) => setState({ status: 'ready', data }), [])
  return { state, reload, replace }
}

/**
 * Turn an expected "not there yet" into `null`.
 *
 * Only the listed canonical codes are absorbed — every other failure stays an
 * error, so a permission or server problem can never masquerade as emptiness.
 */
export async function optional<T>(promise: Promise<T>, codes: readonly string[]): Promise<T | null> {
  try {
    return await promise
  } catch (error) {
    if (error instanceof ApiError && codes.includes(error.code)) return null
    throw error
  }
}
