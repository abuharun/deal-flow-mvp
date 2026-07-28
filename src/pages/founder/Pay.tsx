import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS } from '../../lib/types'
import { VALIDATION_FEE } from '../../lib/seed'
import { useLocale } from '../../i18n'
import { StubTag } from '../../components/ui'
import { useToast } from '../../components/toast'

export default function Pay() {
  const { state, founderStartup, pay } = useStore()
  const { t } = useLocale()
  const navigate = useNavigate()
  const toast = useToast()
  const [processing, setProcessing] = useState(false)
  const [declined, setDeclined] = useState(false)

  if (founderStartup) return <Navigate to="/apply" replace />

  const incomplete = STEP_KEYS.filter((k) => !state.draft.completed.includes(k))
  if (incomplete.length > 0) {
    return <Navigate to={`/apply/submit?step=${incomplete[0]}`} replace />
  }

  const runPayment = (ok: boolean) => {
    setDeclined(false)
    setProcessing(true)
    // Simulated gateway round-trip. No real payment exists in this demo.
    setTimeout(() => {
      pay(ok)
      setProcessing(false)
      if (ok) {
        toast(t.pay.toastPaid)
        navigate('/apply')
      } else {
        setDeclined(true)
      }
    }, 900)
  }

  return (
    <div>
      <h1 style={{ fontSize: '1.6rem' }}>{t.pay.title}</h1>
      <p className="muted" style={{ maxWidth: 540 }}>
        {t.pay.intro}
      </p>

      <div className="card" style={{ margin: '20px 0' }}>
        <div className="panel-title">
          <h2 style={{ margin: 0, fontSize: '1.05rem' }}>{t.pay.orderSummary}</h2>
          <StubTag>{t.pay.stubPayment}</StubTag>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderTop: '1px solid var(--line)' }}>
          <span>{t.pay.lineItem(state.draft.startupName)}</span>
          <span className="num">{VALIDATION_FEE}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderTop: '1px solid var(--line)', fontWeight: 640 }}>
          <span>{t.pay.totalDue}</span>
          <span className="num">{VALIDATION_FEE}</span>
        </div>
      </div>

      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault()
          runPayment(true)
        }}
      >
        <div className="field">
          <label htmlFor="card-number">{t.pay.cardNumber}</label>
          <input id="card-number" className="input" inputMode="numeric" defaultValue="4242 4242 4242 4242" autoComplete="cc-number" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="field">
            <label htmlFor="card-exp">{t.pay.expiry}</label>
            <input id="card-exp" className="input" defaultValue="12/28" autoComplete="cc-exp" />
          </div>
          <div className="field">
            <label htmlFor="card-cvc">{t.pay.cvc}</label>
            <input id="card-cvc" className="input" defaultValue="123" autoComplete="cc-csc" />
          </div>
        </div>
        {declined && (
          <p className="error-text" role="alert">
            {t.pay.declined}
          </p>
        )}
        <div style={{ display: 'grid', gap: 10, marginTop: 6 }}>
          <button type="submit" className="btn btn-primary btn-lg" disabled={processing}>
            {processing ? t.pay.processing : t.pay.payButton(VALIDATION_FEE)}
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            disabled={processing}
            onClick={() => runPayment(false)}
          >
            {t.pay.simulateDeclined}
          </button>
        </div>
      </form>

      <p className="faint" style={{ marginTop: 16 }}>
        <Link to="/apply/submit?step=ask">{t.pay.backToSubmit}</Link> {t.pay.backNote}
      </p>
    </div>
  )
}
