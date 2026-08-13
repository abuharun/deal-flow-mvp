/**
 * The founder's real startup list: GET /founder/startups, nothing else.
 *
 * The list renders exactly what the API returned — no seeded rows, no
 * placeholder startup, and no optimistic entry. An account with no startups
 * shows an empty state that says so.
 */

import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import * as founderApi from '../../api/founder'
import type { StartupResponse } from '../../api/types'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { useResource } from '../useResource'
import { EmptyPanel, ErrorPanel, LoadingPanel, NotWiredYet } from '../states'

export function StatusChip({ startup }: { startup: StartupResponse }) {
  const { t } = useLocale()
  return <span className={`status-chip status-${startup.status}`}>{t.work.status[startup.status]}</span>
}

export default function StartupList() {
  const { callApi } = useAuth()
  const { locale, t } = useLocale()

  const load = useCallback(
    (signal: AbortSignal) => callApi((auth) => founderApi.listStartups({ ...auth, signal }), signal),
    [callApi],
  )
  const { state, reload } = useResource(load)

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
          {/* Creating a startup is a real API route; the form is not in this slice. */}
          <NotWiredYet label={t.work.createButton} />
        </div>
      </div>

      {state.status === 'loading' && <LoadingPanel />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ready' &&
        (state.data.length === 0 ? (
          <EmptyPanel title={t.work.listEmptyTitle} body={t.work.listEmptyBody} />
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
