/**
 * One in-flight write against the API, with explicit busy and error state.
 *
 * Deliberately fire-and-forget from the caller's point of view: a click
 * handler calls `run(...)` and never has to `await` or `try`. A rejection is
 * captured into `error` (the same `ApiError` the client throws), so the UI
 * always has the backend's own canonical reason to show instead of a generic
 * failure — and a mutation that failed never leaves a control stuck in its
 * busy state.
 *
 * Concurrency: a second `run` while one is in flight is ignored rather than
 * queued. Double-clicking "approve" must not send two approvals.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface Mutation<Args extends unknown[]> {
  busy: boolean
  /** The last failure, or null. Cleared when a new attempt starts. */
  error: unknown
  run: (...args: Args) => void
  /** Dismiss a failure without retrying. */
  reset: () => void
}

/**
 * `perform` must be referentially stable (wrap it in `useCallback`) — it is
 * captured in `run`'s dependency list.
 */
export function useMutation<Args extends unknown[]>(
  perform: (...args: Args) => Promise<void>,
): Mutation<Args> {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const mounted = useRef(true)
  // A ref, not `busy`: state updates are async, so two clicks in the same
  // tick would both see busy === false.
  const inFlight = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(
    (...args: Args) => {
      if (inFlight.current) return
      inFlight.current = true
      setBusy(true)
      setError(null)
      void perform(...args)
        .catch((cause: unknown) => {
          if (mounted.current) setError(cause)
        })
        .finally(() => {
          inFlight.current = false
          if (mounted.current) setBusy(false)
        })
    },
    [perform],
  )

  const reset = useCallback(() => setError(null), [])
  return { busy, error, run, reset }
}
