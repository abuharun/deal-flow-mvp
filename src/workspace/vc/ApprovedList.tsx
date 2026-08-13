/**
 * The investor's list of founder-approved startups (GET /vc/startups).
 *
 * Only startups whose founder explicitly approved a narrative appear here —
 * that is the backend's rule, and this page adds nothing to it. Paging is the
 * API's own bounded limit/offset.
 */

import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import * as vcApi from '../../api/vc'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { useResource } from '../useResource'
import { EmptyPanel, ErrorPanel, LoadingPanel } from '../states'

export default function ApprovedList() {
  const { callApi } = useAuth()
  const { locale, t } = useLocale()
  const [offset, setOffset] = useState(0)

  const load = useCallback(
    (signal: AbortSignal) =>
      callApi((auth) => vcApi.listApprovedStartups({ ...auth, signal }, { offset }), signal),
    [callApi, offset],
  )
  const { state, reload } = useResource(load)

  return (
    <section className="workspace-section">
      <div className="workspace-head">
        <div>
          <h1>{t.work.vcListTitle}</h1>
          <p className="muted">{t.work.vcListLede}</p>
        </div>
        <button type="button" className="btn btn-quiet btn-sm" onClick={reload}>
          {t.work.refresh}
        </button>
      </div>

      {state.status === 'loading' && <LoadingPanel />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ready' &&
        (state.data.items.length === 0 ? (
          <EmptyPanel title={t.work.vcListEmptyTitle} body={t.work.vcListEmptyBody} />
        ) : (
          <>
            <p className="faint">{t.work.vcTotal(state.data.total)}</p>
            <ul className="startup-cards">
              {state.data.items.map((startup) => (
                <li key={startup.id}>
                  <Link to={`/investor/${startup.id}`} className="card startup-card">
                    <div className="startup-card-head">
                      <h2>{startup.name}</h2>
                      <span className="faint">
                        {t.work.vcApprovedAt}: {formatDate(startup.approved_at, locale)}
                      </span>
                    </div>
                    {startup.one_liner && <p className="muted">{startup.one_liner}</p>}
                    <p className="faint">
                      {[startup.sector, startup.funding_stage, startup.city].filter(Boolean).join(' · ')}
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
            {state.data.total > state.data.limit && (
              <div className="list-toolbar">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(offset - state.data.limit, 0))}
                >
                  {t.work.vcPrev}
                </button>
                <span className="faint">
                  {t.work.vcPage(offset + 1, offset + state.data.items.length, state.data.total)}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={offset + state.data.limit >= state.data.total}
                  onClick={() => setOffset(offset + state.data.limit)}
                >
                  {t.work.vcNext}
                </button>
              </div>
            )}
          </>
        ))}
    </section>
  )
}
