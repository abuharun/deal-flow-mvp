import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS, type Attachment, type StepKey } from '../../lib/types'
import { STEP_META } from './steps'
import { cx } from '../../lib/format'
import { StubTag } from '../../components/ui'
import { DocIcon } from '../../components/icons'

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
          ? "Davom etishdan oldin startap nomini kiriting va savolga javob bering."
          : "Davom etishdan oldin bu bo'limga javob bering — bo'sh bo'limni ko'rib chiqib bo'lmaydi.",
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
      <nav aria-label="Topshirish bosqichlari">
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
        {STEP_KEYS.length} bosqichdan {stepIndex + 1}-si
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
              <label htmlFor="f-name">Startap nomi</label>
              <input
                id="f-name"
                className="input"
                value={draft.startupName}
                onChange={(e) => updateDraft({ startupName: e.target.value })}
                placeholder="Masalan: Xarid"
                autoComplete="organization"
              />
            </div>
            <div className="field">
              <label htmlFor="f-oneliner">Bir qatorli tavsif</label>
              <input
                id="f-oneliner"
                className="input"
                value={draft.oneLiner}
                onChange={(e) => updateDraft({ oneLiner: e.target.value })}
                placeholder="Masalan: Restoranlar uchun B2B ta'minot marketpleysi"
              />
            </div>
            <div className="field">
              <label htmlFor="f-sector">Soha</label>
              <input
                id="f-sector"
                className="input"
                value={draft.sector}
                onChange={(e) => updateDraft({ sector: e.target.value })}
                placeholder="Masalan: Fintech, Logistika, EdTech"
              />
            </div>
            <div className="field">
              <label htmlFor="f-stage">Moliyalash bosqichi</label>
              <select
                id="f-stage"
                className="select"
                value={draft.fundingStage}
                onChange={(e) => updateDraft({ fundingStage: e.target.value })}
              >
                <option value="">Tanlang…</option>
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
              <label htmlFor="f-revenue">Oylik daromad (bo'lsa)</label>
              <input
                id="f-revenue"
                className="input"
                value={draft.revenue}
                onChange={(e) => updateDraft({ revenue: e.target.value })}
                placeholder="Masalan: oyiga $24 700 — yoki «hali daromadsiz»"
              />
            </div>
            <div className="field">
              <label htmlFor="f-growth">O'sish</label>
              <input
                id="f-growth"
                className="input"
                value={draft.growth}
                onChange={(e) => updateDraft({ growth: e.target.value })}
                placeholder="Masalan: oyiga +18%"
              />
            </div>
          </>
        )}

        {step === 'ask' && (
          <>
            <div className="field">
              <label htmlFor="f-ask">Jalb qilinayotgan summa, qisqacha</label>
              <input
                id="f-ask"
                className="input"
                value={draft.ask}
                onChange={(e) => updateDraft({ ask: e.target.value })}
                placeholder="Masalan: $500k seed"
              />
            </div>
            <fieldset style={{ border: 'none', padding: 0, margin: '0 0 18px' }}>
              <legend style={{ fontWeight: 580, fontSize: '0.92rem', padding: 0, marginBottom: 6 }}>
                Ilovalar <StubTag>Demo yuklash — fayllar saqlanmaydi</StubTag>
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
                        aria-label={`${a.label} faylini olib tashlash`}
                      >
                        Olib tashlash
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
                    + {s.label} biriktirish
                  </button>
                ))}
              </div>
            </fieldset>
          </>
        )}

        <div aria-live="polite" className="autosave-note">
          {draft.updatedAt
            ? "Shu qurilmada saqlandi — istalgan payt chiqib, keyin qaytishingiz mumkin."
            : 'Javoblaringiz yozganingiz sari avtomatik saqlanadi.'}
        </div>

        <div className="step-actions">
          {stepIndex > 0 ? (
            <Link to={`/apply/submit?step=${STEP_KEYS[stepIndex - 1]}`} className="btn btn-secondary">
              Orqaga
            </Link>
          ) : (
            <Link to="/apply" className="btn btn-quiet">
              Saqlash va chiqish
            </Link>
          )}
          <button type="submit" className="btn btn-primary">
            {stepIndex === STEP_KEYS.length - 1 ? "To'lovga o'tish" : 'Davom etish'}
          </button>
        </div>
      </form>
    </div>
  )
}
