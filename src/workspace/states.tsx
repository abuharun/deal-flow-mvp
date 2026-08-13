/**
 * The four honest answers a backend-connected panel can give: loading, error,
 * empty, or locked. Nothing here ever invents content — an empty list says it
 * is empty, and a failure says what failed and offers a retry.
 */

import type { ReactNode } from 'react'
import { ApiError, NETWORK_ERROR_CODE } from '../api/client'
import { useLocale } from '../i18n'

/** Map a canonical backend error code onto localized, non-technical copy. */
export function useApiMessage(): (error: unknown) => string {
  const { t } = useLocale()
  return (error: unknown) => {
    if (!(error instanceof ApiError)) return t.apiError.fallback
    return t.apiError[error.code] ?? t.apiError.fallback
  }
}

export function LoadingPanel({ label }: { label?: string }) {
  const { t } = useLocale()
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <span className="state-spinner" aria-hidden="true" />
      <p className="muted">{label ?? t.work.loading}</p>
    </div>
  )
}

export function ErrorPanel({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useLocale()
  const message = useApiMessage()(error)
  const requestId = error instanceof ApiError && error.code !== NETWORK_ERROR_CODE ? error.requestId : ''
  return (
    <div className="state-panel state-error" role="alert">
      <p>{message}</p>
      {requestId && <p className="faint state-request-id">ID: {requestId}</p>}
      {onRetry && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          {t.work.retry}
        </button>
      )}
    </div>
  )
}

export function EmptyPanel({ title, body, children }: { title: string; body?: string; children?: ReactNode }) {
  return (
    <div className="state-panel state-empty">
      <h3>{title}</h3>
      {body && <p className="muted">{body}</p>}
      {children}
    </div>
  )
}

/** Shown wherever an approved (frozen) startup would otherwise offer an edit. */
export function LockedNotice() {
  const { t } = useLocale()
  return (
    <div className="notice notice-locked">
      <strong>{t.work.lockedTitle}</strong>
      <p className="muted">{t.work.lockedBody}</p>
    </div>
  )
}

/**
 * A capability that exists in the API but is not wired into this slice yet.
 * It is deliberately inert and clearly labelled — never a disabled control
 * that pretends the feature is one click away.
 */
export function NotWiredYet({ label }: { label: string }) {
  return <span className="stub-tag stub-pending">{label}</span>
}
