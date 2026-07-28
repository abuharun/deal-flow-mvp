import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { StubTag } from '../../components/ui'
import { useToast } from '../../components/toast'

export default function Settings() {
  const { state, resetDemo, logout } = useStore()
  const navigate = useNavigate()
  const toast = useToast()
  const [confirmReset, setConfirmReset] = useState(false)

  return (
    <div className="settings-grid">
      <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Sozlamalar</h1>

      <section className="card" aria-labelledby="s-profile">
        <h2 id="s-profile" style={{ fontSize: '1.05rem' }}>
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
            <dt className="muted">Rol</dt>
            <dd style={{ margin: 0 }}>Ko'rib chiquvchi hamkor — O'zbekiston piloti</dd>
          </div>
        </dl>
      </section>

      <section className="card" aria-labelledby="s-letter">
        <div className="panel-title">
          <h2 id="s-letter" style={{ fontSize: '1.05rem', margin: 0 }}>
            Xulosa xatlari
          </h2>
          <StubTag>Demo — faqat ko'rsatish uchun</StubTag>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="sig-name">Xatlardagi imzo</label>
          <input id="sig-name" className="input" defaultValue={`${state.session?.name} — Oqim hamkori`} />
          <p className="hint">Siz yuboradigan har bir xulosa xatining imzo qismida chiqadi.</p>
        </div>
      </section>

      <section className="card" aria-labelledby="s-notify">
        <div className="panel-title">
          <h2 id="s-notify" style={{ fontSize: '1.05rem', margin: 0 }}>
            Bildirishnomalar
          </h2>
          <StubTag>Demo — faqat ko'rsatish uchun</StubTag>
        </div>
        {[
          ["Pipeline'ga yangi arizalar tushganda", true],
          ["«Yangi» ustunining kunlik xulosasi", true],
          ["Asoschi yuborilgan xulosaga javob berganda", false],
        ].map(([label, on]) => (
          <label key={label as string} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 0' }}>
            <input type="checkbox" defaultChecked={on as boolean} style={{ width: 17, height: 17, accentColor: 'var(--brand)' }} />
            {label}
          </label>
        ))}
      </section>

      <section className="card" aria-labelledby="s-demo">
        <h2 id="s-demo" style={{ fontSize: '1.05rem' }}>
          Demo boshqaruvi
        </h2>
        <p className="muted">
          Qayta o'rnatish namunaviy pipeline'ni tiklaydi hamda demo asoschining arizasini va siz qabul
          qilgan qarorlarni o'chiradi.
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

      <div>
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
    </div>
  )
}
