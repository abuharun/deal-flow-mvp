import { Link } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS } from '../../lib/types'
import { STEP_META } from './steps'
import { formatDate, DECISION_LABEL } from '../../lib/format'
import { ClockIcon } from '../../components/icons'
import { StubTag } from '../../components/ui'

export default function FounderHome() {
  const { state, founderStartup } = useStore()
  const draft = state.draft
  const started = draft.updatedAt !== null
  const nextStep = STEP_KEYS.find((k) => !draft.completed.includes(k)) ?? 'ask'
  const verdictSent = founderStartup?.verdict?.sentAt

  // Decision ready
  if (founderStartup && verdictSent) {
    return (
      <section aria-labelledby="status-heading">
        <p className="status-chip" style={{ color: 'var(--green-ink)' }}>
          Decision ready
        </p>
        <h1 id="status-heading" style={{ marginTop: 14 }}>
          Your verdict is here, {state.session?.name.split(' ')[0]}.
        </h1>
        <p className="muted" style={{ maxWidth: 520 }}>
          The partner has completed the review of <strong>{founderStartup.name}</strong> and written you
          an honest, reasoned verdict: <strong>{DECISION_LABEL[founderStartup.verdict!.decision]}</strong>.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '20px 0 28px' }}>
          <Link to="/apply/verdict" className="btn btn-primary btn-lg">
            View your verdict
          </Link>
          <Link to="/apply/verdict/letter.pdf" className="btn btn-secondary">
            Verdict letter (PDF)
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
            {founderStartup.name} is under review
          </h1>
          <p className="muted" style={{ maxWidth: 460, margin: '0 auto' }}>
            A real partner reads every submission — no instant judgments here. Honest timing: most
            reviews complete within <strong>five working days</strong>. We'll notify you the moment a
            decision is ready.
          </p>
          <p className="faint" style={{ marginTop: 10 }}>
            Submitted {formatDate(founderStartup.submittedAt)} · validation fee paid
          </p>
        </div>
        <ol className="timeline" style={{ marginTop: 26 }}>
          <li className="done">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Submitted</strong>
              <p className="faint" style={{ margin: 0 }}>
                Your six sections and attachments are in.
              </p>
            </div>
          </li>
          <li className="done">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Standardized</strong>
              <p className="faint" style={{ margin: 0 }}>
                Your story was structured into the format investors read. A human sees your raw words too
                — always.
              </p>
            </div>
          </li>
          <li className="current">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Partner review</strong>
              <p className="faint" style={{ margin: 0 }}>
                A venture partner is reviewing and verifying your claims.
              </p>
            </div>
          </li>
          <li>
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Your verdict</strong>
              <p className="faint" style={{ margin: 0 }}>
                An honest decision with the reason, in your language.
              </p>
            </div>
          </li>
        </ol>
        <div className="demo-note" style={{ marginTop: 24 }}>
          <StubTag>Demo</StubTag> To play the other side: log out, sign in as the VC partner, open{' '}
          <strong>{founderStartup.name}</strong> in the pipeline, decide, and send the verdict. Then
          return here.
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
        <p className="status-chip">Submission in progress</p>
        <h1 id="status-heading" style={{ marginTop: 14 }}>
          Welcome back{draft.startupName ? ` — ${draft.startupName}` : ''}.
        </h1>
        <p className="muted" style={{ maxWidth: 520 }}>
          Your progress is saved on this device. You've completed{' '}
          <span className="num">{doneCount}</span> of <span className="num">6</span> sections — pick up
          right where you left off.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 20 }}>
          <Link to={`/apply/submit?step=${nextStep}`} className="btn btn-primary btn-lg">
            Continue — {STEP_META[nextStep].title}
          </Link>
        </div>
      </section>
    )
  }

  // Empty
  return (
    <section aria-labelledby="status-heading">
      <h1 id="status-heading">Let's find out if your startup is fundable.</h1>
      <p className="muted" style={{ maxWidth: 540 }}>
        You'll answer six honest questions about your business — problem, product, market, traction,
        team, and your ask. It takes 20–30 minutes, saves as you go, and works fine on a phone. A real
        venture partner reviews every submission and writes you a truthful verdict.
      </p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 22 }}>
        <Link to="/apply/submit?step=problem" className="btn btn-primary btn-lg">
          Submit your startup
        </Link>
      </div>
      <hr className="divider" />
      <h2 style={{ fontSize: '1.1rem' }}>What happens after you submit</h2>
      <ol className="timeline">
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>Validation fee</strong>
            <p className="faint" style={{ margin: 0 }}>
              A one-time fee gates the review — it keeps every submission serious, including ours.
            </p>
          </div>
        </li>
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>Partner review</strong>
            <p className="faint" style={{ margin: 0 }}>
              Standardized by AI, judged by a human. Most reviews finish within five working days.
            </p>
          </div>
        </li>
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>Your verdict</strong>
            <p className="faint" style={{ margin: 0 }}>
              A clear decision with the reason — and if the answer is "not yet," what would change it.
            </p>
          </div>
        </li>
      </ol>
    </section>
  )
}

function SubmittedSummary() {
  const { founderStartup } = useStore()
  if (!founderStartup) return null
  return (
    <details className="card card-tight">
      <summary style={{ cursor: 'pointer', fontWeight: 620 }}>
        Your submitted startup — {founderStartup.name}
      </summary>
      <div style={{ marginTop: 12 }}>
        <p className="muted" style={{ marginBottom: 14 }}>
          {founderStartup.oneLiner}
        </p>
        {STEP_KEYS.map((k) => (
          <div className="summary-section" key={k}>
            <h4>{STEP_META[k].title}</h4>
            <p>{founderStartup.raw[k] || <span className="faint">Not provided.</span>}</p>
          </div>
        ))}
      </div>
    </details>
  )
}
