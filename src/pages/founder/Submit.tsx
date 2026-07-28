import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS, type Attachment, type StepKey } from '../../lib/types'
import { STEP_META } from './steps'
import { cx } from '../../lib/format'
import { StubTag } from '../../components/ui'
import { DocIcon } from '../../components/icons'

const SAMPLE_ATTACHMENTS: Attachment[] = [
  { label: 'Pitch deck', kind: 'deck', fileName: 'my-pitch-deck.pdf' },
  { label: 'Revenue proof', kind: 'revenue', fileName: 'bank-statement-export.xlsx' },
  { label: 'Data-room link', kind: 'dataroom', fileName: 'drive.google.com/my-dataroom' },
]

export default function Submit() {
  const { state, founderStartup } = useStore()
  const [params] = useSearchParams()

  // Already submitted — the form is closed; the status home takes over.
  if (founderStartup) return <Navigate to="/apply" replace />

  const requested = params.get('step') as StepKey | null
  const nextIncomplete = STEP_KEYS.find((k) => !state.draft.completed.includes(k)) ?? 'ask'
  const step: StepKey = requested && STEP_KEYS.includes(requested) ? requested : nextIncomplete

  return <StepForm key={step} step={step} />
}

function StepForm({ step }: { step: StepKey }) {
  const { state, updateDraft, completeStep, addDraftAttachment, removeDraftAttachment } = useStore()
  const navigate = useNavigate()
  const meta = STEP_META[step]
  const stepIndex = STEP_KEYS.indexOf(step)
  const draft = state.draft
  const [error, setError] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  // Announce and focus the step heading on step change (focus management).
  useEffect(() => {
    headingRef.current?.focus()
  }, [step])

  const valid =
    draft.fields[step].trim().length > 0 && (step !== 'problem' || draft.startupName.trim().length > 0)

  const goNext = () => {
    if (!valid) {
      setError(
        step === 'problem' && !draft.startupName.trim()
          ? 'Please add your startup name and answer the question before continuing.'
          : 'Please answer this section before continuing — a blank section cannot be reviewed.',
      )
      return
    }
    completeStep(step)
    if (stepIndex === STEP_KEYS.length - 1) {
      navigate('/apply/submit/pay')
    } else {
      navigate(`/apply/submit?step=${STEP_KEYS[stepIndex + 1]}`)
    }
  }

  return (
    <div>
      <nav aria-label="Submission progress">
        <ol className="stepper">
          {STEP_KEYS.map((k) => {
            const done = draft.completed.includes(k)
            const current = k === step
            return (
              <li key={k}>
                <Link
                  to={`/apply/submit?step=${k}`}
                  className={cx(done && 'done', current && 'current')}
                  aria-current={current ? 'step' : undefined}
                >
                  {STEP_META[k].title}
                </Link>
              </li>
            )
          })}
        </ol>
      </nav>

      <p className="faint" style={{ margin: '0 0 4px' }}>
        Step {stepIndex + 1} of {STEP_KEYS.length}
      </p>
      <h1 ref={headingRef} tabIndex={-1} style={{ fontSize: '1.6rem', outline: 'none' }}>
        {meta.question}
      </h1>
      <p className="muted" style={{ maxWidth: 560 }}>
        {meta.hint}
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          goNext()
        }}
      >
        {step === 'problem' && (
          <>
            <div className="field">
              <label htmlFor="f-name">Startup name</label>
              <input
                id="f-name"
                className="input"
                value={draft.startupName}
                onChange={(e) => updateDraft({ startupName: e.target.value })}
                placeholder="e.g. Xarid"
                autoComplete="organization"
              />
            </div>
            <div className="field">
              <label htmlFor="f-oneliner">One-line description</label>
              <input
                id="f-oneliner"
                className="input"
                value={draft.oneLiner}
                onChange={(e) => updateDraft({ oneLiner: e.target.value })}
                placeholder="e.g. B2B procurement marketplace for restaurants"
              />
            </div>
            <div className="field">
              <label htmlFor="f-sector">Sector</label>
              <input
                id="f-sector"
                className="input"
                value={draft.sector}
                onChange={(e) => updateDraft({ sector: e.target.value })}
                placeholder="e.g. Fintech, Logistics, EdTech"
              />
            </div>
            <div className="field">
              <label htmlFor="f-stage">Funding stage</label>
              <select
                id="f-stage"
                className="select"
                value={draft.fundingStage}
                onChange={(e) => updateDraft({ fundingStage: e.target.value })}
              >
                <option value="">Choose…</option>
                <option>Pre-seed</option>
                <option>Seed</option>
                <option>Series A</option>
              </select>
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor={`f-${step}`}>{meta.title}</label>
          <textarea
            id={`f-${step}`}
            className="textarea"
            value={draft.fields[step]}
            onChange={(e) => {
              setError(null)
              updateDraft({}, { [step]: e.target.value })
            }}
            placeholder={meta.placeholder}
            rows={7}
          />
          {error && (
            <p className="error-text" role="alert">
              {error}
            </p>
          )}
        </div>

        {step === 'traction' && (
          <>
            <div className="field">
              <label htmlFor="f-revenue">Monthly revenue (if any)</label>
              <input
                id="f-revenue"
                className="input"
                value={draft.revenue}
                onChange={(e) => updateDraft({ revenue: e.target.value })}
                placeholder="e.g. $24,700 / month — or “pre-revenue”"
              />
            </div>
            <div className="field">
              <label htmlFor="f-growth">Growth</label>
              <input
                id="f-growth"
                className="input"
                value={draft.growth}
                onChange={(e) => updateDraft({ growth: e.target.value })}
                placeholder="e.g. +18% month over month"
              />
            </div>
          </>
        )}

        {step === 'ask' && (
          <>
            <div className="field">
              <label htmlFor="f-ask">Raise amount, in short</label>
              <input
                id="f-ask"
                className="input"
                value={draft.ask}
                onChange={(e) => updateDraft({ ask: e.target.value })}
                placeholder="e.g. $500k seed"
              />
            </div>
            <fieldset style={{ border: 'none', padding: 0, margin: '0 0 18px' }}>
              <legend style={{ fontWeight: 580, fontSize: '0.92rem', padding: 0, marginBottom: 6 }}>
                Attachments <StubTag>Demo upload — files aren't stored</StubTag>
              </legend>
              {draft.attachments.length > 0 && (
                <ul className="attach-list" style={{ marginBottom: 10 }}>
                  {draft.attachments.map((a) => (
                    <li key={a.fileName}>
                      <DocIcon />
                      <span>
                        <strong>{a.label}</strong> · {a.fileName}
                      </span>
                      <button
                        type="button"
                        className="btn btn-quiet btn-sm"
                        style={{ marginLeft: 'auto' }}
                        onClick={() => removeDraftAttachment(a.fileName)}
                        aria-label={`Remove ${a.label}`}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {SAMPLE_ATTACHMENTS.filter(
                  (s) => !draft.attachments.some((a) => a.fileName === s.fileName),
                ).map((s) => (
                  <button
                    key={s.fileName}
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => addDraftAttachment(s)}
                  >
                    + Attach {s.label.toLowerCase()}
                  </button>
                ))}
              </div>
            </fieldset>
          </>
        )}

        <div aria-live="polite" className="autosave-note">
          {draft.updatedAt
            ? 'Saved on this device — you can leave and come back anytime.'
            : 'Your answers save automatically as you type.'}
        </div>

        <div className="step-actions">
          {stepIndex > 0 ? (
            <Link to={`/apply/submit?step=${STEP_KEYS[stepIndex - 1]}`} className="btn btn-secondary">
              Back
            </Link>
          ) : (
            <Link to="/apply" className="btn btn-quiet">
              Save &amp; exit
            </Link>
          )}
          <button type="submit" className="btn btn-primary">
            {stepIndex === STEP_KEYS.length - 1 ? 'Continue to payment' : 'Continue'}
          </button>
        </div>
      </form>
    </div>
  )
}
