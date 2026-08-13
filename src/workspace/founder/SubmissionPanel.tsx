/**
 * The six answers, the optional financials, and the one-way submit.
 *
 * The editor is always open rather than hidden behind an "edit" toggle: the
 * six answers ARE the application, and there is no autosave, so the founder
 * must be able to see and change them without ceremony. Saving PATCHes only
 * the fields that changed — the backend bumps `input_revision` per
 * transaction, and every untouched field it receives is a field it has to
 * consider changed.
 *
 * Submitting is separate and explicit. It never happens as a side effect of
 * saving, and a startup that the backend has already frozen (`vc_visible`)
 * renders as read-only text with no control at all, matching the 409
 * STARTUP_LOCKED every write would otherwise get.
 */

import { useState } from 'react'
import type { StartupDetailResponse, SubmissionPatchRequest } from '../../api/types'
import { ANSWER_KEYS, type AnswerKey } from '../../api/types'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { ErrorPanel } from '../states'

type AnswerDraft = Record<AnswerKey, string>

function draftFrom(startup: StartupDetailResponse): AnswerDraft {
  return Object.fromEntries(ANSWER_KEYS.map((key) => [key, startup.submission[key]])) as AnswerDraft
}

/** Only the answers that differ from what the API last returned. */
function changedAnswers(before: AnswerDraft, after: AnswerDraft): SubmissionPatchRequest {
  const changes: SubmissionPatchRequest = {}
  for (const key of ANSWER_KEYS) {
    if (after[key] !== before[key]) changes[key] = after[key]
  }
  return changes
}

export function useAnswerLabels(): Record<AnswerKey, string> {
  const { t } = useLocale()
  return {
    problem: t.work.answerProblem,
    product: t.work.answerProduct,
    market: t.work.answerMarket,
    traction: t.work.answerTraction,
    team: t.work.answerTeam,
    ask: t.work.answerAsk,
  }
}

export default function SubmissionPanel({
  startup,
  locked,
  saving,
  saveError,
  onSave,
  submitting,
  submitError,
  onSubmit,
}: {
  startup: StartupDetailResponse
  locked: boolean
  saving: boolean
  saveError: unknown
  onSave: (changes: SubmissionPatchRequest) => void
  submitting: boolean
  submitError: unknown
  onSubmit: () => void
}) {
  const { locale, t } = useLocale()
  const labels = useAnswerLabels()
  const saved = draftFrom(startup)
  const [draft, setDraft] = useState<AnswerDraft>(saved)

  if (locked) {
    return (
      <div className="step-body">
        {ANSWER_KEYS.map((key) => (
          <div key={key} className="answer-readonly">
            <h4>{labels[key]}</h4>
            <p>{startup.submission[key] || t.work.notAvailable}</p>
          </div>
        ))}
        {startup.submitted_at && (
          <p className="faint">
            {t.work.submittedAtLabel}: {formatDate(startup.submitted_at, locale)}
          </p>
        )}
      </div>
    )
  }

  const changes = changedAnswers(saved, draft)
  const dirty = Object.keys(changes).length > 0

  return (
    <div className="step-body">
      <p className="muted">{t.work.submissionLede}</p>
      {ANSWER_KEYS.map((key) => (
        <div className="field" key={key}>
          <label htmlFor={`answer-${key}`}>{labels[key]}</label>
          <textarea
            id={`answer-${key}`}
            className="input"
            rows={3}
            value={draft[key]}
            onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
          />
        </div>
      ))}
      {saveError !== null && saveError !== undefined && <ErrorPanel error={saveError} />}
      <div className="list-toolbar">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={saving || !dirty}
          onClick={() => onSave(changes)}
        >
          {saving ? t.work.saving : t.work.submissionSave}
        </button>
      </div>

      {startup.submitted_at ? (
        <p className="faint">
          {t.work.submittedAtLabel}: {formatDate(startup.submitted_at, locale)}
        </p>
      ) : (
        <>
          <p className="muted">{t.work.submitBody}</p>
          {submitError !== null && submitError !== undefined && <ErrorPanel error={submitError} />}
          <button type="button" className="btn btn-primary btn-sm" disabled={submitting} onClick={onSubmit}>
            {submitting ? t.work.submitBusy : t.work.submitButton}
          </button>
        </>
      )}
    </div>
  )
}
