/**
 * The founder's real startup list, and the one place a startup is created.
 *
 * The list renders exactly what GET /founder/startups returned — no seeded
 * rows, no placeholder startup, and no optimistic entry: a created startup
 * appears because the API answered 201 with it, and the app navigates to the
 * id the API chose rather than one it guessed.
 */

import { useCallback, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as founderApi from '../../api/founder'
import type { StartupResponse } from '../../api/types'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { useMutation } from '../mutation'
import { useResource } from '../useResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../states'
import { StartupForm, createPayload, type MetadataDraft } from './StartupForm'

export function StatusChip({ startup }: { startup: StartupResponse }) {
  const { t } = useLocale()
  return <span className={`status-chip status-${startup.status}`}>{t.work.status[startup.status]}</span>
}

export default function StartupList() {
  const { callApi } = useAuth()
  const { locale, t } = useLocale()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  const load = useCallback(
    (signal: AbortSignal) => callApi((auth) => founderApi.listStartups({ ...auth, signal }), signal),
    [callApi],
  )
  const { state, reload } = useResource(load)

  const create = useMutation(
    useCallback(
      async (draft: MetadataDraft) => {
        const created = await callApi((auth) => founderApi.createStartup(createPayload(draft), auth))
        setCreating(false)
        navigate(`/founder/${created.id}`)
      },
      [callApi, navigate],
    ),
  )

  return (
    <section className="workspace-section">
      <div className="workspace-head">
        <div>
          <h1>{t.work.listTitle}</h1>
          <p className="muted">{t.work.listLede}</p>
        </div>
        <div className="list-toolbar">
          <button type="button" className="btn btn-quiet btn-sm" onClick={reload}>
            {t.work.refresh}
          </button>
          {!creating && (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => setCreating(true)}>
              {t.work.createButton}
            </button>
          )}
        </div>
      </div>

      {creating && (
        <>
          <h2>{t.work.createTitle}</h2>
          <StartupForm
            idPrefix="create"
            busy={create.busy}
            error={create.error}
            submitLabel={t.work.save}
            onSubmit={create.run}
            onCancel={() => {
              create.reset()
              setCreating(false)
            }}
          />
        </>
      )}

      {state.status === 'loading' && <LoadingPanel />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ready' &&
        (state.data.length === 0 ? (
          !creating && <EmptyPanel title={t.work.listEmptyTitle} body={t.work.listEmptyBody} />
        ) : (
          <ul className="startup-cards">
            {state.data.map((startup) => (
              <li key={startup.id}>
                <Link to={`/founder/${startup.id}`} className="card startup-card">
                  <div className="startup-card-head">
                    <h2>{startup.name}</h2>
                    <StatusChip startup={startup} />
                  </div>
                  {startup.one_liner && <p className="muted">{startup.one_liner}</p>}
                  <dl className="startup-card-meta">
                    {startup.sector && (
                      <div>
                        <dt>{t.work.sectorLabel}</dt>
                        <dd>{startup.sector}</dd>
                      </div>
                    )}
                    {startup.funding_stage && (
                      <div>
                        <dt>{t.work.fundingStageLabel}</dt>
                        <dd>{startup.funding_stage}</dd>
                      </div>
                    )}
                    <div>
                      <dt>{t.work.updatedAtLabel}</dt>
                      <dd>{formatDate(startup.updated_at, locale)}</dd>
                    </div>
                  </dl>
                </Link>
              </li>
            ))}
          </ul>
        ))}
    </section>
  )
}
