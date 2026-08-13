/**
 * The text an investor will actually read: edit it, and see every version.
 *
 * The narrative is seeded from the report by the backend on first read, so
 * this panel never composes text of its own — it edits what the API returned.
 * Each save that changes the text appends an immutable version; the history
 * is loaded only when the founder opens it, because the list endpoint exists
 * to be browsed, not to be fetched on every page load.
 *
 * A blank save is refused here rather than sent: the backend's 422 says the
 * same thing, but losing the editor's contents to a round-trip would be a
 * worse way to learn it.
 */

import { useCallback, useState } from 'react'
import * as founderApi from '../../api/founder'
import type {
  NarrativeCurrentResponse,
  NarrativeVersionListResponse,
  NarrativeVersionResponse,
} from '../../api/types'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { useMutation } from '../mutation'
import { ErrorPanel } from '../states'

function sourceLabel(source: NarrativeCurrentResponse['source'], t: ReturnType<typeof useLocale>['t']): string {
  return source === 'report_seed' ? t.work.narrativeSourceSeed : t.work.narrativeSourceEdit
}

function VersionHistory({ startupId }: { startupId: string }) {
  const { callApi } = useAuth()
  const { locale, t } = useLocale()
  const [list, setList] = useState<NarrativeVersionListResponse | null>(null)
  const [shown, setShown] = useState<NarrativeVersionResponse | null>(null)

  const load = useMutation(
    useCallback(async () => {
      setList(await callApi((auth) => founderApi.listNarrativeVersions(startupId, auth)))
    }, [callApi, startupId]),
  )
  const view = useMutation(
    useCallback(
      async (version: number) => {
        setShown(await callApi((auth) => founderApi.getNarrativeVersion(startupId, version, auth)))
      },
      [callApi, startupId],
    ),
  )

  if (list === null) {
    return (
      <>
        {load.error !== null && <ErrorPanel error={load.error} />}
        <button type="button" className="btn btn-quiet btn-sm" disabled={load.busy} onClick={() => load.run()}>
          {load.busy ? t.work.loading : t.work.versionsTitle}
        </button>
      </>
    )
  }

  return (
    <div className="version-history">
      <h4>{t.work.versionsTitle}</h4>
      {view.error !== null && <ErrorPanel error={view.error} />}
      <ul className="version-list" aria-label={t.work.versionsTitle}>
        {list.versions.map((entry) => (
          <li key={entry.version}>
            <span>
              {t.work.narrativeVersion(entry.version)}
              {entry.version === list.current_version && <span className="faint"> · {t.work.versionsCurrent}</span>}
            </span>
            <span className="faint">
              {sourceLabel(entry.source, t)} · {t.work.versionLength(entry.content_length)} ·{' '}
              {formatDate(entry.created_at, locale)}
            </span>
            <button
              type="button"
              className="btn btn-quiet btn-sm"
              disabled={view.busy}
              onClick={() => view.run(entry.version)}
            >
              {t.work.versionView}
            </button>
          </li>
        ))}
      </ul>
      {shown && (
        <div className="version-preview">
          <p className="faint">{t.work.narrativeVersion(shown.version)}</p>
          <p className="narrative-text">{shown.content}</p>
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => setShown(null)}>
            {t.work.versionClose}
          </button>
        </div>
      )}
    </div>
  )
}

export default function NarrativePanel({
  startupId,
  narrative,
  locked,
  saving,
  saveError,
  onSave,
}: {
  startupId: string
  narrative: NarrativeCurrentResponse | null
  locked: boolean
  saving: boolean
  saveError: unknown
  onSave: (content: string) => void
}) {
  const { t } = useLocale()
  const [draft, setDraft] = useState(narrative?.content ?? '')

  if (narrative === null) {
    return (
      <div className="step-body">
        <p className="muted">{t.work.narrativeNotReady}</p>
      </div>
    )
  }

  const meta = (
    <p className="faint">
      {t.work.narrativeVersion(narrative.version)} · {sourceLabel(narrative.source, t)}
    </p>
  )

  if (locked) {
    return (
      <div className="step-body">
        {meta}
        <p className="narrative-text">{narrative.content}</p>
      </div>
    )
  }

  return (
    <div className="step-body">
      {meta}
      <p className="muted">{t.work.narrativeLede}</p>
      <div className="field">
        <label htmlFor="narrative-content">{t.work.narrativeLabel}</label>
        <textarea
          id="narrative-content"
          className="input"
          rows={10}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </div>
      {saveError !== null && saveError !== undefined && <ErrorPanel error={saveError} />}
      <div className="list-toolbar">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={saving || draft.trim().length === 0}
          onClick={() => onSave(draft.trim())}
        >
          {saving ? t.work.saving : t.work.narrativeSave}
        </button>
      </div>
      <VersionHistory startupId={startupId} />
    </div>
  )
}
