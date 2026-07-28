import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS, type Attachment, type StepKey } from '../../lib/types'
import { useLocale } from '../../i18n'
import { attachmentLabel } from '../../lib/content'
import { cx } from '../../lib/format'
import { StubTag } from '../../components/ui'
import { DocIcon } from '../../components/icons'

// Labels are stored canonically in Uzbek and localized at display time, so a
// draft attached under one interface language reads correctly under the other.
const SAMPLE_ATTACHMENTS: Attachment[] = [
  { label: 'Pitch-dek', kind: 'deck', fileName: 'my-pitch-deck.pdf' },
  { label: 'Daromad isboti', kind: 'revenue', fileName: 'bank-statement-export.xlsx' },
  { label: 'Data room havolasi', kind: 'dataroom', fileName: 'drive.google.com/my-dataroom' },
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
  const { locale, t } = useLocale()
  const navigate = useNavigate()
  const meta = t.steps[step]
  const stepIndex = STEP_KEYS.indexOf(step)
  const draft = state.draft
  const [error, setError] = useState<'name' | 'empty' | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  // Announce and focus the step heading on step change (focus management).
  useEffect(() => {
    headingRef.current?.focus()
  }, [step])

  const valid =
    draft.fields[step].trim().length > 0 && (step !== 'problem' || draft.startupName.trim().length > 0)

  const goNext = () => {
    if (!valid) {
      setError(step === 'problem' && !draft.startupName.trim() ? 'name' : 'empty')
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
      <nav aria-label={t.submit.stepsNavAria}>
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
                  {t.steps[k].title}
                </Link>
              </li>
            )
          })}
        </ol>
      </nav>

      <p className="faint" style={{ margin: '0 0 4px' }}>
        {t.submit.stepOf(stepIndex + 1, STEP_KEYS.length)}
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
              <label htmlFor="f-name">{t.submit.startupName}</label>
              <input
                id="f-name"
                className="input"
                value={draft.startupName}
                onChange={(e) => updateDraft({ startupName: e.target.value })}
                placeholder={t.submit.startupNamePlaceholder}
                autoComplete="organization"
              />
            </div>
            <div className="field">
              <label htmlFor="f-oneliner">{t.submit.oneLiner}</label>
              <input
                id="f-oneliner"
                className="input"
                value={draft.oneLiner}
                onChange={(e) => updateDraft({ oneLiner: e.target.value })}
                placeholder={t.submit.oneLinerPlaceholder}
              />
            </div>
            <div className="field">
              <label htmlFor="f-sector">{t.submit.sector}</label>
              <input
                id="f-sector"
                className="input"
                value={draft.sector}
                onChange={(e) => updateDraft({ sector: e.target.value })}
                placeholder={t.submit.sectorPlaceholder}
              />
            </div>
            <div className="field">
              <label htmlFor="f-stage">{t.submit.fundingStage}</label>
              <select
                id="f-stage"
                className="select"
                value={draft.fundingStage}
                onChange={(e) => updateDraft({ fundingStage: e.target.value })}
              >
                <option value="">{t.submit.choose}</option>
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
              {error === 'name' ? t.submit.errName : t.submit.errEmpty}
            </p>
          )}
        </div>

        {step === 'traction' && (
          <>
            <div className="field">
              <label htmlFor="f-revenue">{t.submit.revenue}</label>
              <input
                id="f-revenue"
                className="input"
                value={draft.revenue}
                onChange={(e) => updateDraft({ revenue: e.target.value })}
                placeholder={t.submit.revenuePlaceholder}
              />
            </div>
            <div className="field">
              <label htmlFor="f-growth">{t.submit.growth}</label>
              <input
                id="f-growth"
                className="input"
                value={draft.growth}
                onChange={(e) => updateDraft({ growth: e.target.value })}
                placeholder={t.submit.growthPlaceholder}
              />
            </div>
          </>
        )}

        {step === 'ask' && (
          <>
            <div className="field">
              <label htmlFor="f-ask">{t.submit.askShort}</label>
              <input
                id="f-ask"
                className="input"
                value={draft.ask}
                onChange={(e) => updateDraft({ ask: e.target.value })}
                placeholder={t.submit.askShortPlaceholder}
              />
            </div>
            <fieldset style={{ border: 'none', padding: 0, margin: '0 0 18px' }}>
              <legend style={{ fontWeight: 580, fontSize: '0.92rem', padding: 0, marginBottom: 6 }}>
                {t.submit.attachments} <StubTag>{t.submit.attachmentsStub}</StubTag>
              </legend>
              {draft.attachments.length > 0 && (
                <ul className="attach-list" style={{ marginBottom: 10 }}>
                  {draft.attachments.map((a) => (
                    <li key={a.fileName}>
                      <DocIcon />
                      <span>
                        <strong>{attachmentLabel(a.label, locale)}</strong> · {a.fileName}
                      </span>
                      <button
                        type="button"
                        className="btn btn-quiet btn-sm"
                        style={{ marginLeft: 'auto' }}
                        onClick={() => removeDraftAttachment(a.fileName)}
                        aria-label={t.submit.removeAttachment(attachmentLabel(a.label, locale))}
                      >
                        {t.submit.remove}
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
                    {t.submit.attach(attachmentLabel(s.label, locale))}
                  </button>
                ))}
              </div>
            </fieldset>
          </>
        )}

        <div aria-live="polite" className="autosave-note">
          {draft.updatedAt ? t.submit.autosaved : t.submit.autosaveIdle}
        </div>

        <div className="step-actions">
          {stepIndex > 0 ? (
            <Link to={`/apply/submit?step=${STEP_KEYS[stepIndex - 1]}`} className="btn btn-secondary">
              {t.common.back}
            </Link>
          ) : (
            <Link to="/apply" className="btn btn-quiet">
              {t.submit.saveExit}
            </Link>
          )}
          <button type="submit" className="btn btn-primary">
            {stepIndex === STEP_KEYS.length - 1 ? t.submit.toPay : t.submit.next}
          </button>
        </div>
      </form>
    </div>
  )
}
