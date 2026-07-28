import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLocale } from '../../i18n'
import { useStore } from '../../lib/store'
import { StubTag } from '../../components/ui'
import { useToast } from '../../components/toast'

export default function Settings() {
  const { state, resetDemo, logout } = useStore()
  const { t } = useLocale()
  const navigate = useNavigate()
  const toast = useToast()
  const [confirmReset, setConfirmReset] = useState(false)

  return (
    <div className="settings-grid">
      <h1 style={{ fontSize: '1.5rem', margin: 0 }}>{t.settings.title}</h1>

      <section className="card" aria-labelledby="s-profile">
        <h2 id="s-profile" style={{ fontSize: '1.05rem' }}>
          {t.common.profile}
        </h2>
        <dl style={{ margin: 0, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">{t.common.name}</dt>
            <dd style={{ margin: 0, fontWeight: 580 }}>{state.session?.name}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">{t.common.email}</dt>
            <dd style={{ margin: 0 }}>{state.session?.email}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">{t.settings.role}</dt>
            <dd style={{ margin: 0 }}>{t.settings.roleValue}</dd>
          </div>
        </dl>
      </section>

      <section className="card" aria-labelledby="s-letter">
        <div className="panel-title">
          <h2 id="s-letter" style={{ fontSize: '1.05rem', margin: 0 }}>
            {t.settings.letters}
          </h2>
          <StubTag>{t.settings.demoOnly}</StubTag>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="sig-name">{t.settings.signature}</label>
          <input
            id="sig-name"
            className="input"
            defaultValue={t.settings.signatureValue(state.session?.name ?? '')}
          />
          <p className="hint">{t.settings.signatureHint}</p>
        </div>
      </section>

      <section className="card" aria-labelledby="s-notify">
        <div className="panel-title">
          <h2 id="s-notify" style={{ fontSize: '1.05rem', margin: 0 }}>
            {t.settings.notifications}
          </h2>
          <StubTag>{t.settings.demoOnly}</StubTag>
        </div>
        {[
          [t.settings.notifNew, true],
          [t.settings.notifDigest, true],
          [t.settings.notifReplies, false],
        ].map(([label, on]) => (
          <label key={label as string} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 0' }}>
            <input type="checkbox" defaultChecked={on as boolean} style={{ width: 17, height: 17, accentColor: 'var(--brand)' }} />
            {label}
          </label>
        ))}
      </section>

      <section className="card" aria-labelledby="s-demo">
        <h2 id="s-demo" style={{ fontSize: '1.05rem' }}>
          {t.settings.demoHeading}
        </h2>
        <p className="muted">{t.settings.demoBody}</p>
        {confirmReset ? (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                resetDemo()
                setConfirmReset(false)
                toast(t.settings.toastReset)
              }}
            >
              {t.settings.resetConfirm}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(false)}>
              {t.common.cancel}
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(true)}>
            {t.settings.resetButton}
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
          {t.common.logout}
        </button>
      </div>
    </div>
  )
}
