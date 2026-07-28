import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS, type Decision, type Signal } from '../../lib/types'
import { useLocale } from '../../i18n'
import { localizeStartup } from '../../lib/content'
import { formatDate, cx } from '../../lib/format'
import { AiBadge, SignalTag, StageBadge, StubTag } from '../../components/ui'
import { CheckIcon, DocIcon } from '../../components/icons'
import { LANG_LABEL } from '../../lib/compose'
import { useToast } from '../../components/toast'

const DECISIONS: Decision[] = ['recommend', 'advance', 'pass']

export default function StartupDetail() {
  const { id } = useParams()
  const { state, setSignal, toggleVerification, setDecision, setNotes, compose, editVerdict, sendVerdict } =
    useStore()
  const { locale, t } = useLocale()
  const toast = useToast()
  const [draftLang, setDraftLang] = useState<'en' | 'local'>('en')
  const [confirmSend, setConfirmSend] = useState(false)
  const reviewRef = useRef<HTMLDivElement>(null)
  const verifyRef = useRef<HTMLDivElement>(null)
  const decideRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)

  const stored = state.startups.find((s) => s.id === id)
  if (!stored) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: 40 }}>
        <h1 style={{ fontSize: '1.2rem' }}>{t.detail.notFoundTitle}</h1>
        <p className="muted">
          {t.detail.notFoundBody(<Link to="/app">{t.detail.backToPipeline}</Link>)}
        </p>
      </div>
    )
  }

  // Display-layer localization; ids and reducer contracts stay untouched.
  const startup = localizeStartup(stored, locale)

  const verifiedCount = startup.verification.filter((v) => v.done).length
  const sent = Boolean(startup.verdict?.sentAt)
  const canCompose = Boolean(startup.decision && startup.notes.trim())

  const scrollTo = (ref: React.RefObject<HTMLDivElement | null>) =>
    ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div>
      <p style={{ marginBottom: 8 }}>
        <Link to="/app" className="faint" style={{ textDecoration: 'none' }}>
          {t.detail.backLink}
        </Link>
      </p>

      <header className="detail-head">
        <div>
          <h1 style={{ marginBottom: 4 }}>{startup.name}</h1>
          <p className="muted" style={{ margin: 0 }}>
            {startup.oneLiner}
          </p>
          <div className="detail-meta">
            <StageBadge stage={startup.stage} />
            <span className="faint">
              {startup.sector} · {startup.fundingStage} · {startup.founder.name}, {startup.founder.city} ·{' '}
              {t.detail.submittedLabel} <span className="num">{formatDate(startup.submittedAt, locale)}</span>
            </span>
          </div>
        </div>
        <div style={{ display: 'grid', gap: 8, justifyItems: 'end' }}>
          <SignalTag signal={startup.signal} overridden={startup.signalOverridden} />
          <label className="faint" htmlFor="retag" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {t.detail.retag}
            <select
              id="retag"
              className="select"
              style={{ width: 'auto', padding: '4px 8px', fontSize: '0.85rem' }}
              value={startup.signal}
              onChange={(e) => setSignal(startup.id, e.target.value as Signal)}
            >
              {(['high', 'medium', 'low'] as Signal[]).map((s) => (
                <option key={s} value={s}>
                  {t.signal[s]}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <nav className="detail-tabs" aria-label={t.detail.tabsAria}>
        <button type="button" onClick={() => scrollTo(reviewRef)}>
          {t.detail.tabReview}
        </button>
        <button type="button" onClick={() => scrollTo(verifyRef)}>
          {t.detail.tabVerify} <span className="num">{verifiedCount}/{startup.verification.length}</span>
        </button>
        <button type="button" onClick={() => scrollTo(decideRef)}>
          {t.detail.tabDecide}
        </button>
        <button type="button" onClick={() => scrollTo(composerRef)}>
          {t.detail.tabVerdict}
        </button>
      </nav>

      {sent && (
        <div className="sent-banner" style={{ marginBottom: 18 }}>
          <CheckIcon />{' '}
          {t.detail.sentBanner(
            formatDate(startup.verdict!.sentAt!, locale),
            t.decision[startup.verdict!.decision],
          )}
        </div>
      )}

      {/* ---- Recommendation ---- */}
      <section className="card ai-frame section-block" aria-labelledby="rec-heading">
        <div className="panel-title">
          <h2 id="rec-heading" style={{ margin: 0, fontSize: '1.05rem' }}>
            {startup.recommendation.headline}
          </h2>
          <AiBadge />
        </div>
        <ul style={{ margin: 0, paddingLeft: 20, display: 'grid', gap: 6 }}>
          {startup.recommendation.rationale.map((r) => (
            <li key={r} className="muted" style={{ fontSize: '0.94rem' }}>
              {r}
            </li>
          ))}
        </ul>
        <p className="faint" style={{ margin: '10px 0 0' }}>
          {t.detail.suggestionNote(t.signal[startup.recommendation.signal].toLowerCase())}
        </p>
      </section>

      <div className="metric-row">
        {(
          [
            [t.detail.metricRevenue, startup.metrics.revenue],
            [t.detail.metricGrowth, startup.metrics.growth],
            [t.detail.metricAsk, startup.metrics.ask],
          ] as Array<[string, string]>
        ).map(([label, value]) => (
          <div className="metric" key={label}>
            <span className="label">{label}</span>
            <div className="value num">{value}</div>
          </div>
        ))}
      </div>

      {/* ---- Review: summary beside raw ---- */}
      <div ref={reviewRef} className="section-block">
        <div className="split">
          <section className="card ai-frame" aria-labelledby="summary-heading">
            <div className="panel-title">
              <h2 id="summary-heading" style={{ margin: 0, fontSize: '1.05rem' }}>
                {t.detail.summaryHeading}
              </h2>
              <AiBadge>{t.badges.aiStandardized}</AiBadge>
            </div>
            {STEP_KEYS.map((k) => (
              <div className="summary-section" key={k}>
                <h4>{t.steps[k].title}</h4>
                <p>{startup.summary[k]}</p>
              </div>
            ))}
          </section>
          <section className="card" aria-labelledby="raw-heading">
            <div className="panel-title">
              <h2 id="raw-heading" style={{ margin: 0, fontSize: '1.05rem' }}>
                {t.detail.rawHeading}
              </h2>
              <span className="faint">{t.detail.rawNote}</span>
            </div>
            {STEP_KEYS.map((k) => (
              <div className="summary-section" key={k}>
                <h4>{t.steps[k].title}</h4>
                <p>{startup.raw[k]}</p>
              </div>
            ))}
          </section>
        </div>
      </div>

      {/* ---- Verification ---- */}
      <div ref={verifyRef} className="card section-block">
        <div className="panel-title">
          <h2 style={{ margin: 0, fontSize: '1.05rem' }}>{t.detail.verification}</h2>
          <span className="faint num" aria-live="polite">
            {t.detail.verifiedCount(verifiedCount, startup.verification.length)}
          </span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          {t.detail.verificationIntro}
        </p>
        <ul className="check-list">
          {startup.verification.map((v) => (
            <li key={v.id} className={cx('check-item', v.done && 'done')}>
              <input
                type="checkbox"
                id={`verify-${v.id}`}
                checked={v.done}
                onChange={() => toggleVerification(startup.id, v.id)}
              />
              <label htmlFor={`verify-${v.id}`}>
                {v.label}
                <span className="hint">{v.hint}</span>
              </label>
            </li>
          ))}
        </ul>
      </div>

      {/* ---- Decision + notes ---- */}
      <div ref={decideRef} className="card section-block">
        <h2 style={{ fontSize: '1.05rem' }}>{t.detail.decisionHeading}</h2>
        <div className="decision-options" role="group" aria-label={t.detail.decisionGroupAria}>
          {DECISIONS.map((d) => (
            <button
              key={d}
              type="button"
              className="decision-option"
              aria-pressed={startup.decision === d}
              disabled={sent}
              onClick={() => setDecision(startup.id, d)}
            >
              <span className="d-title">{t.decision[d]}</span>
              <span className="d-sub">{t.detail.decisionSub[d]}</span>
            </button>
          ))}
        </div>
        <div className="field" style={{ marginBottom: 8 }}>
          <label htmlFor="rough-notes">{t.detail.notesLabel}</label>
          <p className="hint">{t.detail.notesHint}</p>
          <textarea
            id="rough-notes"
            className="textarea"
            value={startup.notes}
            disabled={sent}
            onChange={(e) => setNotes(startup.id, e.target.value)}
            placeholder={t.detail.notesPlaceholder}
          />
        </div>
        {!sent && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={!canCompose}
            onClick={() => {
              // Seeded demo notes may be displayed in Russian while state still
              // holds the Uzbek original; compose from what the reviewer sees.
              if (startup.notes !== stored.notes) setNotes(startup.id, startup.notes)
              compose(startup.id)
              setConfirmSend(false)
              setDraftLang('en')
              toast(t.detail.composeToast)
              setTimeout(() => scrollTo(composerRef), 50)
            }}
          >
            {startup.verdict ? t.detail.recomposeButton : t.detail.composeButton}
          </button>
        )}
        {!canCompose && !sent && (
          <p className="faint" style={{ marginTop: 8 }}>
            {t.detail.composeGate}
          </p>
        )}
      </div>

      {/* ---- Verdict composer ---- */}
      <div ref={composerRef} className="section-block">
        {startup.verdict ? (
          <section className="card ai-frame" aria-labelledby="composer-heading">
            <div className="panel-title" style={{ flexWrap: 'wrap' }}>
              <h2 id="composer-heading" style={{ margin: 0, fontSize: '1.05rem' }}>
                {sent ? t.detail.composerSent : t.detail.composerDraft}
              </h2>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                {startup.verdict.edited && !sent && <StubTag>{t.detail.editedTag}</StubTag>}
                <AiBadge>{t.detail.fromNotesBadge}</AiBadge>
              </div>
            </div>

            <div className="lang-toggle" role="group" aria-label={t.detail.draftLangAria} style={{ marginBottom: 12 }}>
              <button type="button" aria-pressed={draftLang === 'en'} onClick={() => setDraftLang('en')}>
                {t.detail.enOriginal}
              </button>
              <button type="button" aria-pressed={draftLang === 'local'} onClick={() => setDraftLang('local')}>
                {t.detail.founderLang(LANG_LABEL[startup.verdict.localLang])}
              </button>
            </div>

            {draftLang === 'en' ? (
              sent ? (
                <div className="verdict-draft" lang="en">{startup.verdict.en}</div>
              ) : (
                <div className="field">
                  <label htmlFor="draft-en">{t.detail.editLabel}</label>
                  <textarea
                    id="draft-en"
                    className="textarea verdict-textarea"
                    lang="en"
                    value={startup.verdict.en}
                    onChange={(e) => editVerdict(startup.id, e.target.value)}
                  />
                </div>
              )
            ) : (
              <>
                <div className="verdict-draft" lang={startup.verdict.localLang}>
                  {startup.verdict.local}
                </div>
                {!sent && (
                  <p className="faint" style={{ marginTop: 10 }}>
                    {t.detail.translationNote}
                  </p>
                )}
              </>
            )}

            {!sent && (
              <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                {confirmSend ? (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        sendVerdict(startup.id)
                        setConfirmSend(false)
                        toast(t.detail.sentToast)
                      }}
                    >
                      {t.detail.confirmSend(startup.founder.name)}
                    </button>
                    <button type="button" className="btn btn-secondary" onClick={() => setConfirmSend(false)}>
                      {t.detail.notNow}
                    </button>
                  </>
                ) : (
                  <button type="button" className="btn btn-primary" onClick={() => setConfirmSend(true)}>
                    {t.detail.sendVerdict}
                  </button>
                )}
                <span className="faint">
                  {t.detail.sendNote(startup.name, t.decision[startup.verdict.decision])}
                </span>
              </div>
            )}
          </section>
        ) : (
          <section className="card" aria-labelledby="composer-heading">
            <h2 id="composer-heading" style={{ fontSize: '1.05rem' }}>
              {t.detail.composerEmptyHeading}
            </h2>
            <p className="muted" style={{ margin: 0 }}>
              {t.detail.composerEmptyBody(t.detail.composeButton, startup.founder.name.split(' ')[0])}
            </p>
          </section>
        )}
      </div>

      {/* ---- Attachments ---- */}
      <section className="card section-block" aria-labelledby="attach-heading">
        <div className="panel-title">
          <h2 id="attach-heading" style={{ margin: 0, fontSize: '1.05rem' }}>
            {t.detail.attachHeading}
          </h2>
          <StubTag>{t.detail.attachStub}</StubTag>
        </div>
        {startup.attachments.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            {t.detail.noAttachments}
          </p>
        ) : (
          <ul className="attach-list">
            {startup.attachments.map((a) => (
              <li key={a.fileName}>
                <DocIcon />
                <span>
                  <strong>{a.label}</strong> · {a.fileName}
                </span>
                <span className="kind">{t.detail.kindLabel[a.kind]}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
