import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS } from '../../lib/types'
import { VALIDATION_FEE } from '../../lib/seed'
import { StubTag } from '../../components/ui'
import { useToast } from '../../components/toast'

export default function Pay() {
  const { state, founderStartup, pay } = useStore()
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
        toast("To'lov qabul qilindi — startapingiz topshirildi.")
        navigate('/apply')
      } else {
        setDeclined(true)
      }
    }, 900)
  }

  return (
    <div>
      <h1 style={{ fontSize: '1.6rem' }}>Oxirgi qadam: baholash to'lovi</h1>
      <p className="muted" style={{ maxWidth: 540 }}>
        Aynan shu to'lov tahlilni jiddiy qiladi — u haqiqiy hamkorning vaqtini va qanday bo'lmasin
        haqqoniy javobni ta'minlaydi. To'lov yakunlanishi bilan startapingiz ko'rib chiqish
        pipeline'iga kiradi.
      </p>

      <div className="card" style={{ margin: '20px 0' }}>
        <div className="panel-title">
          <h2 style={{ margin: 0, fontSize: '1.05rem' }}>Buyurtma xulosasi</h2>
          <StubTag>Simulyatsiya qilingan to'lov — kartadan pul yechilmaydi</StubTag>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderTop: '1px solid var(--line)' }}>
          <span>
            Startap baholovi — <strong>{state.draft.startupName}</strong>
          </span>
          <span className="num">{VALIDATION_FEE}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderTop: '1px solid var(--line)', fontWeight: 640 }}>
          <span>Bugun to'lanadigan jami</span>
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
          <label htmlFor="card-number">Karta raqami</label>
          <input id="card-number" className="input" inputMode="numeric" defaultValue="4242 4242 4242 4242" autoComplete="cc-number" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div className="field">
            <label htmlFor="card-exp">Amal muddati</label>
            <input id="card-exp" className="input" defaultValue="12/28" autoComplete="cc-exp" />
          </div>
          <div className="field">
            <label htmlFor="card-cvc">CVC</label>
            <input id="card-cvc" className="input" defaultValue="123" autoComplete="cc-csc" />
          </div>
        </div>
        {declined && (
          <p className="error-text" role="alert">
            Kartangiz rad etildi (simulyatsiya). Kiritgan ma'lumotlaringiz saqlanib turibdi — tayyor bo'lganingizda
            qayta urinib ko'ring.
          </p>
        )}
        <div style={{ display: 'grid', gap: 10, marginTop: 6 }}>
          <button type="submit" className="btn btn-primary btn-lg" disabled={processing}>
            {processing ? 'Bajarilmoqda…' : `${VALIDATION_FEE} to'lash va topshirish`}
          </button>
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            disabled={processing}
            onClick={() => runPayment(false)}
          >
            Rad etilgan kartani simulyatsiya qilish
          </button>
        </div>
      </form>

      <p className="faint" style={{ marginTop: 16 }}>
        <Link to="/apply/submit?step=ask">Topshirishga qaytish</Link> — to'lov yakunlanmaguncha hech
        narsa yuborilmaydi.
      </p>
    </div>
  )
}
