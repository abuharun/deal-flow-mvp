import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { formatDate } from '../../lib/format'
import { StubTag } from '../../components/ui'
import { useToast } from '../../components/toast'

export default function FounderAccount() {
  const { state, resetDemo, logout } = useStore()
  const navigate = useNavigate()
  const toast = useToast()
  const [confirmReset, setConfirmReset] = useState(false)

  return (
    <div>
      <h1 style={{ fontSize: '1.6rem' }}>Hisob</h1>

      <section className="card section-block" aria-labelledby="profile-heading">
        <h2 id="profile-heading" style={{ fontSize: '1.05rem' }}>
          Profil
        </h2>
        <dl style={{ margin: 0, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">Ism</dt>
            <dd style={{ margin: 0, fontWeight: 580 }}>{state.session?.name}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">Email</dt>
            <dd style={{ margin: 0 }}>{state.session?.email}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">Afzal til</dt>
            <dd style={{ margin: 0 }}>O'zbekcha (xulosalar o'z tilingizda keladi)</dd>
          </div>
        </dl>
      </section>

      <section className="card section-block" aria-labelledby="billing-heading">
        <div className="panel-title">
          <h2 id="billing-heading" style={{ fontSize: '1.05rem', margin: 0 }}>
            To'lovlar tarixi
          </h2>
          <StubTag>Simulyatsiya qilingan to'lovlar</StubTag>
        </div>
        {state.payments.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            Hozircha to'lovlar yo'q. Topshirishni yakunlaganingizda baholash to'lovi shu yerda ko'rinadi.
          </p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 8 }}>
            {state.payments.map((p) => (
              <li
                key={p.id}
                style={{ display: 'flex', justifyContent: 'space-between', gap: 12, borderTop: '1px solid var(--line)', paddingTop: 8 }}
              >
                <span>
                  {p.label}
                  <span className="faint" style={{ display: 'block' }}>
                    {formatDate(p.date)}
                  </span>
                </span>
                <span className="num" style={{ color: p.status === 'failed' ? 'var(--red-ink)' : undefined }}>
                  {p.amount} {p.status === 'failed' ? '· rad etilgan' : "· to'langan"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card section-block" aria-labelledby="demo-heading">
        <h2 id="demo-heading" style={{ fontSize: '1.05rem' }}>
          Demo boshqaruvi
        </h2>
        <p className="muted">
          Qayta o'rnatish butun demoni — topshirgan startapingiz, to'lovlaringiz va investor pipeline'ini — dastlabki
          namunaviy holatiga qaytaradi.
        </p>
        {confirmReset ? (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                resetDemo()
                setConfirmReset(false)
                toast("Demo ma'lumotlari dastlabki holatiga qaytarildi.")
              }}
            >
              Ha, hammasini qayta o'rnatish
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(false)}>
              Bekor qilish
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(true)}>
            Demo ma'lumotlarini qayta o'rnatish
          </button>
        )}
      </section>

      <button
        type="button"
        className="btn btn-quiet"
        onClick={() => {
          logout()
          navigate('/')
        }}
      >
        Chiqish
      </button>
    </div>
  )
}
