/**
 * One startup's real progress, assembled from the API's own answers.
 *
 * Every panel below is a READ of a specific backend resource. Where a
 * resource legitimately does not exist yet, the API says so with a canonical
 * 404/409 and the panel reports that absence — it never fills the gap with
 * sample content. Mutations (upload, pay, consent, trigger, edit, approve)
 * are real API routes that this slice does not wire yet; each is marked as
 * such instead of being faked or silently disabled.
 */

import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as founderApi from '../../api/founder'
import type {
  AnalysisJobResponse,
  ConsentSummaryResponse,
  DeckResponse,
  NarrativeApprovalResponse,
  NarrativeCurrentResponse,
  PaymentResponse,
  StartupDetailResponse,
} from '../../api/types'
import { ANSWER_KEYS } from '../../api/types'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatBytes, formatDate } from '../../lib/format'
import { computeProgress, isLocked, type StepId, type WorkspaceSnapshot } from '../progress'
import { optional, useResource } from '../useResource'
import { ErrorPanel, LoadingPanel, LockedNotice, NotWiredYet } from '../states'
import { StatusChip } from './StartupList'

interface DetailSnapshot extends WorkspaceSnapshot {
  startup: StartupDetailResponse
}

/** Canonical "not there yet" codes, per backend router docstrings. */
const ABSENT = {
  deck: ['DECK_NOT_FOUND'],
  payment: ['PAYMENT_NOT_FOUND'],
  analysis: ['ANALYSIS_NOT_FOUND'],
  narrative: ['NARRATIVE_NOT_READY'],
  approval: ['NARRATIVE_NOT_APPROVED', 'NARRATIVE_NOT_READY'],
} as const

function StepRow({ id, state, children }: { id: StepId; state: string; children?: React.ReactNode }) {
  const { t } = useLocale()
  const label: Record<StepId, string> = {
    submission: t.work.stepSubmission,
    deck: t.work.stepDeck,
    payment: t.work.stepPayment,
    consent: t.work.stepConsent,
    analysis: t.work.stepAnalysis,
    narrative: t.work.stepNarrative,
    approval: t.work.stepApproval,
  }
  const stateLabel: Record<string, string> = {
    done: t.work.stepStateDone,
    current: t.work.stepStateCurrent,
    todo: t.work.stepStateTodo,
    locked: t.work.stepStateLocked,
  }
  return (
    <li className={`progress-step step-${state}`}>
      <div className="progress-step-head">
        <h3>{label[id]}</h3>
        <span className={`step-state step-state-${state}`}>{stateLabel[state]}</span>
      </div>
      {children}
    </li>
  )
}

function SubmissionPanel({ startup }: { startup: StartupDetailResponse }) {
  const { locale, t } = useLocale()
  const answered = ANSWER_KEYS.filter((key) => startup.submission[key].trim().length > 0)
  const answerLabels: Record<string, string> = {
    problem: t.work.answerProblem,
    product: t.work.answerProduct,
    market: t.work.answerMarket,
    traction: t.work.answerTraction,
    team: t.work.answerTeam,
    ask: t.work.answerAsk,
  }
  return (
    <div className="step-body">
      <p className="muted">
        {answered.length}/{ANSWER_KEYS.length} · {ANSWER_KEYS.map((key) => answerLabels[key]).join(' · ')}
      </p>
      {startup.submitted_at ? (
        <p className="faint">
          {t.work.submittedAtLabel}: {formatDate(startup.submitted_at, locale)}
        </p>
      ) : (
        <NotWiredYet label={t.work.submitButton} />
      )}
    </div>
  )
}

function DeckPanel({ deck }: { deck: DeckResponse | null }) {
  const { locale, t } = useLocale()
  if (!deck) {
    return (
      <div className="step-body">
        <p className="muted">{t.work.deckNone}</p>
        <NotWiredYet label={t.work.deckUpload} />
      </div>
    )
  }
  return (
    <div className="step-body">
      <p>
        <strong>{deck.filename}</strong>
      </p>
      <p className="faint">
        {t.work.deckPages(deck.page_count)} · {formatBytes(deck.size_bytes, locale)} · {t.work.deckUploadedAt}:{' '}
        {formatDate(deck.uploaded_at, locale)}
      </p>
      <NotWiredYet label={t.work.deckReplace} />
    </div>
  )
}

function PaymentPanel({ payment }: { payment: PaymentResponse | null }) {
  const { locale, t } = useLocale()
  return (
    <div className="step-body">
      <p className="demo-note">{t.work.paymentDemoNotice}</p>
      {payment ? (
        <p>
          {payment.status === 'paid' ? t.work.paymentStatusPaid : t.work.paymentStatusFailed}
          {payment.paid_at && <span className="faint"> · {formatDate(payment.paid_at, locale)}</span>}
        </p>
      ) : (
        <>
          <p className="muted">{t.work.paymentNone}</p>
          <NotWiredYet label={t.work.paymentPay} />
        </>
      )}
    </div>
  )
}

function ConsentPanel({ consents }: { consents: ConsentSummaryResponse | null }) {
  const { t } = useLocale()
  if (!consents) return null
  return (
    <div className="step-body">
      <p className="muted">{t.work.consentBody}</p>
      <p className="faint">{t.work.consentVersion(consents.current_version)}</p>
      {consents.granted ? <p>{t.work.consentGranted}</p> : <NotWiredYet label={t.work.consentGrant} />}
    </div>
  )
}

function AnalysisPanel({ analysis }: { analysis: AnalysisJobResponse | null }) {
  const { locale, t } = useLocale()
  if (!analysis) {
    return (
      <div className="step-body">
        <p className="muted">{t.work.analysisNone}</p>
        <NotWiredYet label={t.work.analysisTrigger} />
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
      {analysis.stale && <p className="error-text">{t.work.analysisStale}</p>}
      {analysis.status === 'failed' && analysis.last_error_code && (
        <p className="error-text">{t.work.analysisFailed(analysis.last_error_code)}</p>
      )}
    </div>
  )
}

function NarrativePanel({ narrative }: { narrative: NarrativeCurrentResponse | null }) {
  const { t } = useLocale()
  if (!narrative) {
    return (
      <div className="step-body">
        <p className="muted">{t.work.narrativeNotReady}</p>
      </div>
    )
  }
  return (
    <div className="step-body">
      <p className="faint">
        {t.work.narrativeVersion(narrative.version)} ·{' '}
        {narrative.source === 'report_seed' ? t.work.narrativeSourceSeed : t.work.narrativeSourceEdit}
      </p>
      <p className="narrative-preview">{narrative.content}</p>
      <NotWiredYet label={t.work.narrativeSave} />
    </div>
  )
}

function ApprovalPanel({
  approval,
  narrative,
}: {
  approval: NarrativeApprovalResponse | null
  narrative: NarrativeCurrentResponse | null
}) {
  const { locale, t } = useLocale()
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
  return (
    <div className="step-body">
      <p className="muted">{t.work.approvalNone}</p>
      {narrative && <NotWiredYet label={t.work.approvalButton(narrative.version)} />}
    </div>
  )
}

export default function StartupDetail() {
  const { startupId = '' } = useParams()
  const { callApi } = useAuth()
  const { locale, t } = useLocale()

  const load = useCallback(
    async (signal: AbortSignal): Promise<DetailSnapshot> =>
      callApi(async (auth) => {
        const call = { ...auth, signal }
        // One round of parallel reads: every panel's data arrives together, so
        // the page never renders half-known progress.
        const [startup, deck, payment, consents, analysis, narrative, approval] = await Promise.all([
          founderApi.getStartup(startupId, call),
          optional(founderApi.getDeckMetadata(startupId, call), ABSENT.deck),
          optional(founderApi.getPayment(startupId, call), ABSENT.payment),
          founderApi.getConsents(startupId, call),
          optional(founderApi.getAnalysis(startupId, call), ABSENT.analysis),
          optional(founderApi.getNarrative(startupId, call), ABSENT.narrative),
          optional(founderApi.getApproval(startupId, call), ABSENT.approval),
        ])
        return { startup, deck, payment, consents, analysis, narrative, approval }
      }, signal),
    [callApi, startupId],
  )
  const { state, reload } = useResource(load)

  if (state.status === 'loading') return <LoadingPanel />
  if (state.status === 'error') return <ErrorPanel error={state.error} onRetry={reload} />

  const snapshot = state.data
  const { startup } = snapshot
  const steps = computeProgress(snapshot)
  const panels: Record<StepId, React.ReactNode> = {
    submission: <SubmissionPanel startup={startup} />,
    deck: <DeckPanel deck={snapshot.deck} />,
    payment: <PaymentPanel payment={snapshot.payment} />,
    consent: <ConsentPanel consents={snapshot.consents} />,
    analysis: <AnalysisPanel analysis={snapshot.analysis} />,
    narrative: <NarrativePanel narrative={snapshot.narrative} />,
    approval: <ApprovalPanel approval={snapshot.approval} narrative={snapshot.narrative} />,
  }

  return (
    <section className="workspace-section">
      <p className="faint">
        <Link to="/founder">← {t.work.listTitle}</Link>
      </p>
      <div className="workspace-head">
        <div>
          <h1>{startup.name}</h1>
          {startup.one_liner && <p className="muted">{startup.one_liner}</p>}
          <p className="faint">
            {[startup.sector, startup.funding_stage, startup.city].filter(Boolean).join(' · ') || t.work.notAvailable}
            {' · '}
            {t.work.updatedAtLabel}: {formatDate(startup.updated_at, locale)}
          </p>
        </div>
        <div className="list-toolbar">
          <StatusChip startup={startup} />
          <button type="button" className="btn btn-quiet btn-sm" onClick={reload}>
            {t.work.refresh}
          </button>
        </div>
      </div>

      {isLocked(startup) && <LockedNotice />}

      <ol className="progress-rail" aria-label={t.work.progressAria}>
        {steps.map((step) => (
          <StepRow key={step.id} id={step.id} state={step.state}>
            {panels[step.id]}
          </StepRow>
        ))}
      </ol>
    </section>
  )
}
