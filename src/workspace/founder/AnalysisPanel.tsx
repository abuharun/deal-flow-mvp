/**
 * Starting the AI research run, and following it until it settles.
 *
 * Preconditions are computed from resources the API already returned (deck,
 * payment, consent, submitted_at), so the panel can name what is still
 * missing without inventing anything. The trigger appears only when all of
 * them hold: the backend would answer 422 ANALYSIS_PRECONDITION with exactly
 * this list, and offering a button whose only possible outcome is that error
 * would be theatre. The server stays authoritative either way — this is a
 * projection of its answers, not a second rule.
 *
 * Polling exists because the run happens in a separate worker process: while
 * the job is queued/running/retrying the panel re-reads GET .../analysis, and
 * the moment it reaches a terminal state it reloads the whole page snapshot
 * once (a completed run is what materializes the narrative) and stops. There
 * is no polling of a finished job and none at all before one exists.
 */

import { useEffect, useRef } from 'react'
import type { AnalysisJobResponse, AnalysisStatus, PreconditionReason } from '../../api/types'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { ErrorPanel } from '../states'
import type { WorkspaceSnapshot } from '../progress'

export const ANALYSIS_POLL_INTERVAL_MS = 3000

const IN_FLIGHT: readonly AnalysisStatus[] = ['queued', 'running', 'retrying']

/**
 * The same four reasons `backend/app/services/ai_precondition.py` evaluates,
 * in its order, derived from what the API already told this page.
 */
export function missingPrerequisites(snapshot: WorkspaceSnapshot): PreconditionReason[] {
  const missing: PreconditionReason[] = []
  if (snapshot.startup.submitted_at === null) missing.push('startup_not_submitted')
  if (snapshot.deck === null) missing.push('deck_missing')
  if (snapshot.payment?.status !== 'paid') missing.push('payment_not_paid')
  if (snapshot.consents?.granted !== true) missing.push('consent_missing')
  return missing
}

export default function AnalysisPanel({
  snapshot,
  locked,
  busy,
  error,
  onTrigger,
  onPoll,
  onSettled,
}: {
  snapshot: WorkspaceSnapshot
  locked: boolean
  busy: boolean
  error: unknown
  onTrigger: () => void
  /** Re-read the job. Must be stable; resolves with the fresh job. */
  onPoll: () => Promise<AnalysisJobResponse | null>
  /** Called once, when a followed job first reaches a terminal state. */
  onSettled: () => void
}) {
  const { locale, t } = useLocale()
  const analysis = snapshot.analysis
  const following = analysis !== null && IN_FLIGHT.includes(analysis.status)
  // Latest callbacks without making them the effect's dependencies: a new
  // closure each render must not restart the interval.
  const poll = useRef(onPoll)
  const settled = useRef(onSettled)
  poll.current = onPoll
  settled.current = onSettled

  useEffect(() => {
    if (!following) return
    let active = true
    const timer = setInterval(() => {
      void poll.current().then((job) => {
        if (!active || job === null) return
        if (!IN_FLIGHT.includes(job.status)) settled.current()
      })
    }, ANALYSIS_POLL_INTERVAL_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [following])

  if (analysis === null) {
    const missing = missingPrerequisites(snapshot)
    return (
      <div className="step-body">
        <p className="muted">{t.work.analysisNone}</p>
        <p className="faint">{t.work.analysisLede}</p>
        {missing.length > 0 ? (
          <>
            <p className="muted">{t.work.preconditionTitle}</p>
            <ul className="precondition-list">
              {missing.map((reason) => (
                <li key={reason}>{t.work.precondition[reason]}</li>
              ))}
            </ul>
          </>
        ) : (
          !locked && (
            <>
              {error !== null && error !== undefined && <ErrorPanel error={error} />}
              <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={onTrigger}>
                {busy ? t.work.analysisBusy : t.work.analysisTrigger}
              </button>
            </>
          )
        )}
      </div>
    )
  }

  return (
    <div className="step-body">
      <p>
        {t.work.analysisStatusLabel}: <strong>{t.work.analysisStatus[analysis.status]}</strong>
        <span className="faint"> · {t.work.analysisAttempts(analysis.attempts, analysis.max_attempts)}</span>
      </p>
      <p className="faint">
        {t.work.analysisQueuedAt}: {formatDate(analysis.queued_at, locale)}
      </p>
      {following && <p className="faint">{t.work.analysisAutoRefresh}</p>}
      {analysis.stale && <p className="error-text">{t.work.analysisStale}</p>}
      {analysis.status === 'failed' && analysis.last_error_code && (
        <p className="error-text">{t.work.analysisFailed(analysis.last_error_code)}</p>
      )}
    </div>
  )
}
