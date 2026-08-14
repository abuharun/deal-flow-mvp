/**
 * One frozen dossier, exactly as the API projects it (GET /vc/startups/{id}).
 *
 * Read-only by construction: there is no control on this page that could
 * change anything, matching a router that exposes no writes at all. The
 * narrative shown is the version the founder approved, and every claim,
 * competitor and checklist row keeps the citation ids that point into the
 * report's own source list.
 */

import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as vcApi from '../../api/vc'
import type { ReportSourceResponse, VcReportBody } from '../../api/types'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { useResource } from '../useResource'
import { ErrorPanel, LoadingPanel } from '../states'
import { ChecklistStatusTag, ConfidenceTag } from '../../components/ui'

/** Citation markers reference the report's own 1-based source ordinals. */
function Citations({ ids }: { ids: number[] }) {
  const { t } = useLocale()
  if (ids.length === 0) return null
  return (
    <span className="citations" aria-label={t.work.citationAria(ids.join(', '))}>
      {ids.map((id) => (
        <sup key={id} className="citation">
          [{id}]
        </sup>
      ))}
    </span>
  )
}

function ReportSections({ report }: { report: VcReportBody }) {
  const { t } = useLocale()
  const sections = [
    { key: 'uzbekistan_central_asia_market', title: t.work.reportSectionMarket },
    { key: 'global_competitors', title: t.work.reportSectionCompetitors },
    { key: 'us_vc_readiness', title: t.work.reportSectionReadiness },
  ] as const
  return (
    <>
      {sections.map(({ key, title }) => (
        <section key={key} className="section-block">
          <h3>{title}</h3>
          <p>
            {report.sections[key].narrative}
            <Citations ids={report.sections[key].citation_ids} />
          </p>
        </section>
      ))}
    </>
  )
}

function SourceList({ sources }: { sources: ReportSourceResponse[] }) {
  const { locale, t } = useLocale()
  return (
    <section className="section-block">
      <h3>{t.work.reportSources}</h3>
      <ol className="source-list">
        {sources.map((source) => (
          <li key={source.ordinal} id={`source-${source.ordinal}`}>
            <a href={source.url} target="_blank" rel="noreferrer noopener">
              {source.title}
            </a>
            <span className="faint">
              {' '}
              {source.source_quality} · <ConfidenceTag level={source.confidence} /> ·{' '}
              {formatDate(source.accessed_date, locale)}
            </span>
            {source.snippet && <p className="muted">{source.snippet}</p>}
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function Dossier() {
  const { startupId = '' } = useParams()
  const { callApi } = useAuth()
  const { locale, t } = useLocale()

  const load = useCallback(
    (signal: AbortSignal) => callApi((auth) => vcApi.getDossier(startupId, { ...auth, signal }), signal),
    [callApi, startupId],
  )
  const { state, reload } = useResource(load)

  if (state.status === 'loading') return <LoadingPanel />
  if (state.status === 'error') return <ErrorPanel error={state.error} onRetry={reload} />

  const { startup, narrative, report } = state.data
  const body = report.report

  return (
    <article className="workspace-section">
      <p className="faint">
        <Link to="/investor">← {t.work.vcBackToList}</Link>
      </p>
      <div className="workspace-head">
        <div>
          <h1>{startup.name}</h1>
          {startup.one_liner && <p className="muted">{startup.one_liner}</p>}
          <p className="faint">
            {[startup.sector, startup.funding_stage, startup.city].filter(Boolean).join(' · ')} · {t.work.vcApprovedAt}
            : {formatDate(startup.approved_at, locale)}
          </p>
        </div>
        <span className="status-chip status-vc_visible">{t.work.vcReadOnly}</span>
      </div>

      <section className="card">
        <h2>{t.work.vcDossierNarrative}</h2>
        <p className="faint">{t.work.narrativeVersion(narrative.version)}</p>
        <p className="narrative-text">{narrative.content}</p>
      </section>

      <section className="card">
        <h2>{t.work.vcDossierReport}</h2>
        <p className="faint">
          {report.schema_version} · {t.work.reportGeneratedAt}: {formatDate(report.generated_at, locale)}
          {report.evidence_count !== null && ` · ${t.work.reportEvidence(report.evidence_count)}`}
        </p>
        {report.partial && <p className="error-text">{t.work.reportPartial}</p>}

        <section className="section-block">
          <h3>{t.work.reportSummary}</h3>
          <p>{body.executive_summary}</p>
        </section>

        <ReportSections report={body} />

        {body.competitors.length > 0 && (
          <section className="section-block">
            <h3>{t.work.reportCompetitors}</h3>
            <ul>
              {body.competitors.map((competitor) => (
                <li key={competitor.name}>
                  <strong>{competitor.name}</strong> <span className="faint">({competitor.region})</span>{' '}
                  {competitor.note}
                  <Citations ids={competitor.citation_ids} />
                </li>
              ))}
            </ul>
          </section>
        )}

        {body.claims.length > 0 && (
          <section className="section-block">
            <h3>{t.work.reportClaims}</h3>
            <ul>
              {body.claims.map((claim) => (
                <li key={claim.statement}>
                  {claim.statement}
                  <span className="faint"> · {t.work.claimSupport[claim.support]} </span>
                  <ConfidenceTag level={claim.confidence} />
                  <Citations ids={claim.citation_ids} />
                </li>
              ))}
            </ul>
          </section>
        )}

        {body.contradictions.length > 0 && (
          <section className="section-block">
            <h3>{t.work.reportContradictions}</h3>
            <ul>
              {body.contradictions.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          </section>
        )}

        {body.unsupported_claims.length > 0 && (
          <section className="section-block">
            <h3>{t.work.reportUnsupported}</h3>
            <ul>
              {body.unsupported_claims.map((entry) => (
                <li key={entry}>{entry}</li>
              ))}
            </ul>
          </section>
        )}

        <section className="section-block">
          <h3>{t.work.reportChecklist}</h3>
          <ul className="check-list">
            {body.readiness_checklist.map((item) => (
              <li key={item.item} className="checklist-row">
                <div className="checklist-row-head">
                  <strong>{item.item}</strong>
                  <ChecklistStatusTag status={item.status} />
                  <ConfidenceTag level={item.confidence} />
                  <Citations ids={item.evidence} />
                </div>
                {item.evidence_gap && <p className="muted">{item.evidence_gap}</p>}
              </li>
            ))}
          </ul>
        </section>

        <SourceList sources={report.sources} />
      </section>
    </article>
  )
}
