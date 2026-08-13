/**
 * The founder's explicit "send this to investors".
 *
 * Two steps on purpose. Approval freezes the narrative and makes the startup
 * VC-visible, and the backend has no undo for it, so a single misplaced click
 * must not be able to do it. The version number is part of the request, not
 * "whatever is current": if another tab saved an edit in between, the API
 * answers 409 NARRATIVE_VERSION_MISMATCH and the founder finds out instead of
 * silently publishing text they never read.
 */

import { useState } from 'react'
import type { NarrativeApprovalResponse, NarrativeCurrentResponse } from '../../api/types'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { ErrorPanel } from '../states'

export default function ApprovalPanel({
  approval,
  narrative,
  locked,
  busy,
  error,
  onApprove,
}: {
  approval: NarrativeApprovalResponse | null
  narrative: NarrativeCurrentResponse | null
  locked: boolean
  busy: boolean
  error: unknown
  onApprove: (version: number) => void
}) {
  const { locale, t } = useLocale()
  const [confirming, setConfirming] = useState(false)

  if (approval) {
    return (
      <div className="step-body">
        <p>{t.work.approvedVersion(approval.version)}</p>
        <p className="faint">
          {t.work.approvedAt}: {formatDate(approval.approved_at, locale)} · {t.work.vcVisibleAt}:{' '}
          {formatDate(approval.vc_visible_at, locale)}
        </p>
      </div>
    )
  }

  if (narrative === null || locked) {
    return (
      <div className="step-body">
        <p className="muted">{t.work.approvalNone}</p>
      </div>
    )
  }

  return (
    <div className="step-body">
      <p className="muted">{t.work.approvalNone}</p>
      <p className="muted">{t.work.approvalBody}</p>
      {error !== null && error !== undefined && <ErrorPanel error={error} />}
      {confirming ? (
        <div className="list-toolbar">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy}
            onClick={() => onApprove(narrative.version)}
          >
            {busy ? t.work.approvalBusy : t.work.approvalConfirm}
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            disabled={busy}
            onClick={() => setConfirming(false)}
          >
            {t.work.cancel}
          </button>
        </div>
      ) : (
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setConfirming(true)}>
          {t.work.approvalButton(narrative.version)}
        </button>
      )}
    </div>
  )
}
