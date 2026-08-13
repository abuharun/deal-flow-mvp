/**
 * One startup's whole path, assembled from the API's own answers.
 *
 * Reads: seven resources fetched together, so the page never renders half-known
 * progress. Where a resource legitimately does not exist yet, the API says so
 * with a canonical 404/409 and the panel reports that absence — it never fills
 * the gap with sample content.
 *
 * Writes: every mutation here is a real call to a documented endpoint, and each
 * one re-reads the snapshot afterwards rather than patching local state. The
 * backend owns `status`, `input_revision`, the narrative version counter and
 * the VC-visible lock; guessing any of them client-side would eventually show
 * the founder something the server does not agree with.
 *
 * Locking: once the founder approves, `status` becomes `vc_visible` and every
 * write answers 409 STARTUP_LOCKED. The panels drop their controls rather than
 * disable them, so nothing on a frozen startup looks one click away.
 */

import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as founderApi from '../../api/founder'
import type {
  AnalysisJobResponse,
  PaymentStatus,
  StartupDetailResponse,
  SubmissionPatchRequest,
} from '../../api/types'
import { useAuth } from '../../auth/session'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { computeProgress, isLocked, type StepId, type WorkspaceSnapshot } from '../progress'
import { useMutation } from '../mutation'
import { optional, useResource } from '../useResource'
import { ErrorPanel, LoadingPanel, LockedNotice } from '../states'
import { StatusChip } from './StartupList'
import { StartupForm, changedFields, draftFrom, type MetadataDraft } from './StartupForm'
import SubmissionPanel from './SubmissionPanel'
import DeckPanel from './DeckPanel'
import { ConsentPanel, PaymentPanel } from './PrerequisitePanels'
import AnalysisPanel from './AnalysisPanel'
import NarrativePanel from './NarrativePanel'
import ApprovalPanel from './ApprovalPanel'

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

/** Save the deck bytes the API returned under the name it recorded. */
function offerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export default function StartupDetail() {
  const { startupId = '' } = useParams()
  const { callApi } = useAuth()
  const { locale, t } = useLocale()
  const [editingProfile, setEditingProfile] = useState(false)

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

  // Every mutation ends in `reload()`: the backend, not this component, is the
  // authority on what the next state of the page is.
  const patchProfile = useMutation(
    useCallback(
      async (changes: Parameters<typeof founderApi.patchStartup>[1]) => {
        await callApi((auth) => founderApi.patchStartup(startupId, changes, auth))
        setEditingProfile(false)
        reload()
      },
      [callApi, startupId, reload],
    ),
  )
  const saveSubmission = useMutation(
    useCallback(
      async (changes: SubmissionPatchRequest) => {
        await callApi((auth) => founderApi.patchSubmission(startupId, changes, auth))
        reload()
      },
      [callApi, startupId, reload],
    ),
  )
  const submit = useMutation(
    useCallback(async () => {
      await callApi((auth) => founderApi.submitStartup(startupId, auth))
      reload()
    }, [callApi, startupId, reload]),
  )
  const uploadDeck = useMutation(
    useCallback(
      async (file: File) => {
        await callApi((auth) => founderApi.uploadDeck(startupId, file, auth))
        reload()
      },
      [callApi, startupId, reload],
    ),
  )
  const deleteDeck = useMutation(
    useCallback(async () => {
      await callApi((auth) => founderApi.deleteDeck(startupId, auth))
      reload()
    }, [callApi, startupId, reload]),
  )
  const downloadDeck = useMutation(
    useCallback(
      async (filename: string) => {
        offerDownload(await callApi((auth) => founderApi.downloadDeck(startupId, auth)), filename)
      },
      [callApi, startupId],
    ),
  )
  const pay = useMutation(
    useCallback(
      async (outcome: PaymentStatus) => {
        await callApi((auth) => founderApi.submitPayment(startupId, outcome, auth))
        reload()
      },
      [callApi, startupId, reload],
    ),
  )
  const grantConsent = useMutation(
    useCallback(
      async (textVersion: string) => {
        await callApi((auth) => founderApi.grantConsent(startupId, textVersion, auth))
        reload()
      },
      [callApi, startupId, reload],
    ),
  )
  const triggerAnalysis = useMutation(
    useCallback(async () => {
      await callApi((auth) => founderApi.triggerAnalysis(startupId, auth))
      reload()
    }, [callApi, startupId, reload]),
  )
  const saveNarrative = useMutation(
    useCallback(
      async (content: string) => {
        await callApi((auth) => founderApi.saveNarrative(startupId, content, auth))
        reload()
      },
      [callApi, startupId, reload],
    ),
  )
  const approve = useMutation(
    useCallback(
      async (version: number) => {
        await callApi((auth) => founderApi.approveNarrative(startupId, version, auth))
        reload()
      },
      [callApi, startupId, reload],
    ),
  )

  /** One poll of the analysis job; a vanished job simply stops the follow. */
  const pollAnalysis = useCallback(
    async (): Promise<AnalysisJobResponse | null> =>
      callApi((auth) => optional(founderApi.getAnalysis(startupId, auth), ABSENT.analysis)),
    [callApi, startupId],
  )

  if (state.status === 'loading') return <LoadingPanel />
  if (state.status === 'error') return <ErrorPanel error={state.error} onRetry={reload} />

  const snapshot = state.data
  const { startup } = snapshot
  const locked = isLocked(startup)
  const steps = computeProgress(snapshot)

  const panels: Record<StepId, React.ReactNode> = {
    submission: (
      <SubmissionPanel
        startup={startup}
        locked={locked}
        saving={saveSubmission.busy}
        saveError={saveSubmission.error}
        onSave={saveSubmission.run}
        submitting={submit.busy}
        submitError={submit.error}
        onSubmit={submit.run}
      />
    ),
    deck: (
      <DeckPanel
        deck={snapshot.deck}
        locked={locked}
        uploading={uploadDeck.busy}
        uploadError={uploadDeck.error}
        onUpload={uploadDeck.run}
        deleting={deleteDeck.busy}
        deleteError={deleteDeck.error}
        onDelete={deleteDeck.run}
        onDownload={() => downloadDeck.run(snapshot.deck?.filename ?? 'deck.pdf')}
      />
    ),
    payment: (
      <PaymentPanel
        payment={snapshot.payment}
        locked={locked}
        busy={pay.busy}
        error={pay.error}
        onPay={pay.run}
      />
    ),
    consent: (
      <ConsentPanel
        consents={snapshot.consents}
        locked={locked}
        busy={grantConsent.busy}
        error={grantConsent.error}
        onGrant={grantConsent.run}
      />
    ),
    analysis: (
      <AnalysisPanel
        snapshot={snapshot}
        locked={locked}
        busy={triggerAnalysis.busy}
        error={triggerAnalysis.error}
        onTrigger={triggerAnalysis.run}
        onPoll={pollAnalysis}
        onSettled={reload}
      />
    ),
    narrative: (
      <NarrativePanel
        startupId={startupId}
        narrative={snapshot.narrative}
        locked={locked}
        saving={saveNarrative.busy}
        saveError={saveNarrative.error}
        onSave={saveNarrative.run}
      />
    ),
    approval: (
      <ApprovalPanel
        approval={snapshot.approval}
        narrative={snapshot.narrative}
        locked={locked}
        busy={approve.busy}
        error={approve.error}
        onApprove={approve.run}
      />
    ),
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
          {!locked && !editingProfile && (
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setEditingProfile(true)}>
              {t.work.editButton}
            </button>
          )}
          <button type="button" className="btn btn-quiet btn-sm" onClick={reload}>
            {t.work.refresh}
          </button>
        </div>
      </div>

      {editingProfile && (
        <StartupForm
          idPrefix="profile"
          initial={startup}
          busy={patchProfile.busy}
          error={patchProfile.error}
          submitLabel={t.work.save}
          onSubmit={(draft: MetadataDraft) => patchProfile.run(changedFields(draftFrom(startup), draft))}
          onCancel={() => {
            patchProfile.reset()
            setEditingProfile(false)
          }}
        />
      )}

      {locked && <LockedNotice />}

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
