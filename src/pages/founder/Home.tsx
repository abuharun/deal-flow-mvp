import { Link } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS } from '../../lib/types'
import { useLocale } from '../../i18n'
import { localizeStartup } from '../../lib/content'
import { formatDate } from '../../lib/format'
import { ClockIcon } from '../../components/icons'
import { StubTag } from '../../components/ui'

export default function FounderHome() {
  const { state, founderStartup } = useStore()
  const { locale, t } = useLocale()
  const draft = state.draft
  const started = draft.updatedAt !== null
  const nextStep = STEP_KEYS.find((k) => !draft.completed.includes(k)) ?? 'ask'
  const verdictSent = founderStartup?.verdict?.sentAt

  // Decision ready
  if (founderStartup && verdictSent) {
    return (
      <section aria-labelledby="status-heading">
        <p className="status-chip" style={{ color: 'var(--green-ink)' }}>
          {t.founderHome.statusReady}
        </p>
        <h1 id="status-heading" style={{ marginTop: 14 }}>
          {t.founderHome.readyHeading(state.session?.name.split(' ')[0] ?? '')}
        </h1>
        <p className="muted" style={{ maxWidth: 520 }}>
          {t.founderHome.readyBody(founderStartup.name, t.decision[founderStartup.verdict!.decision])}
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '20px 0 28px' }}>
          <Link to="/apply/verdict" className="btn btn-primary btn-lg">
            {t.founderHome.viewVerdict}
          </Link>
          <Link to="/apply/verdict/letter.pdf" className="btn btn-secondary">
            {t.founderHome.letterPdf}
          </Link>
        </div>
        <SubmittedSummary />
      </section>
    )
  }

  // Under review
  if (founderStartup) {
    return (
      <section aria-labelledby="status-heading">
        <div className="pending-hero card">
          <div className="glyph">
            <ClockIcon />
          </div>
          <h1 id="status-heading" style={{ fontSize: '1.6rem' }}>
            {t.founderHome.pendingHeading(founderStartup.name)}
          </h1>
          <p className="muted" style={{ maxWidth: 460, margin: '0 auto' }}>
            {t.founderHome.pendingBody}
          </p>
          <p className="faint" style={{ marginTop: 10 }}>
            {t.founderHome.submittedOn(formatDate(founderStartup.submittedAt, locale))}
          </p>
        </div>
        <ol className="timeline" style={{ marginTop: 26 }}>
          <li className="done">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>{t.founderHome.tlSubmitted}</strong>
              <p className="faint" style={{ margin: 0 }}>
                {t.founderHome.tlSubmittedSub}
              </p>
            </div>
          </li>
          <li className="done">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>{t.founderHome.tlStandardized}</strong>
              <p className="faint" style={{ margin: 0 }}>
                {t.founderHome.tlStandardizedSub}
              </p>
            </div>
          </li>
          <li className="current">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>{t.founderHome.tlPartner}</strong>
              <p className="faint" style={{ margin: 0 }}>
                {t.founderHome.tlPartnerSub}
              </p>
            </div>
          </li>
          <li>
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>{t.founderHome.tlVerdict}</strong>
              <p className="faint" style={{ margin: 0 }}>
                {t.founderHome.tlVerdictSub}
              </p>
            </div>
          </li>
        </ol>
        <div className="demo-note" style={{ marginTop: 24 }}>
          <StubTag>{t.founderHome.demoTag}</StubTag> {t.founderHome.demoPlay(founderStartup.name)}
        </div>
        <div style={{ marginTop: 20 }}>
          <SubmittedSummary />
        </div>
      </section>
    )
  }

  // Draft in progress
  if (started) {
    const doneCount = draft.completed.length
    return (
      <section aria-labelledby="status-heading">
        <p className="status-chip">{t.founderHome.draftChip}</p>
        <h1 id="status-heading" style={{ marginTop: 14 }}>
          {t.founderHome.welcomeBack(draft.startupName || null)}
        </h1>
        <p className="muted" style={{ maxWidth: 520 }}>
          {t.founderHome.draftProgress(doneCount, STEP_KEYS.length)}
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 20 }}>
          <Link to={`/apply/submit?step=${nextStep}`} className="btn btn-primary btn-lg">
            {t.founderHome.continueCta(t.steps[nextStep].title)}
          </Link>
        </div>
      </section>
    )
  }

  // Empty
  return (
    <section aria-labelledby="status-heading">
      <h1 id="status-heading">{t.founderHome.emptyHeading}</h1>
      <p className="muted" style={{ maxWidth: 540 }}>
        {t.founderHome.emptyBody}
      </p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 22 }}>
        <Link to="/apply/submit?step=problem" className="btn btn-primary btn-lg">
          {t.founderHome.submitCta}
        </Link>
      </div>
      <hr className="divider" />
      <h2 style={{ fontSize: '1.1rem' }}>{t.founderHome.afterHeading}</h2>
      <ol className="timeline">
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>{t.founderHome.afterFee}</strong>
            <p className="faint" style={{ margin: 0 }}>
              {t.founderHome.afterFeeSub}
            </p>
          </div>
        </li>
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>{t.founderHome.afterPartner}</strong>
            <p className="faint" style={{ margin: 0 }}>
              {t.founderHome.afterPartnerSub}
            </p>
          </div>
        </li>
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>{t.founderHome.afterVerdict}</strong>
            <p className="faint" style={{ margin: 0 }}>
              {t.founderHome.afterVerdictSub}
            </p>
          </div>
        </li>
      </ol>
    </section>
  )
}

function SubmittedSummary() {
  const { founderStartup } = useStore()
  const { locale, t } = useLocale()
  if (!founderStartup) return null
  const startup = localizeStartup(founderStartup, locale)
  return (
    <details className="card card-tight">
      <summary style={{ cursor: 'pointer', fontWeight: 620 }}>
        {t.founderHome.submittedSummaryTitle(startup.name)}
      </summary>
      <div style={{ marginTop: 12 }}>
        <p className="muted" style={{ marginBottom: 14 }}>
          {startup.oneLiner}
        </p>
        {STEP_KEYS.map((k) => (
          <div className="summary-section" key={k}>
            <h4>{t.steps[k].title}</h4>
            <p>{startup.raw[k] || <span className="faint">{t.founderHome.notFilled}</span>}</p>
          </div>
        ))}
      </div>
    </details>
  )
}
