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
      <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Settings</h1>

      <section className="card" aria-labelledby="s-profile">
        <h2 id="s-profile" style={{ fontSize: '1.05rem' }}>
          Profile
        </h2>
        <dl style={{ margin: 0, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">Name</dt>
            <dd style={{ margin: 0, fontWeight: 580 }}>{state.session?.name}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">Email</dt>
            <dd style={{ margin: 0 }}>{state.session?.email}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">Role</dt>
            <dd style={{ margin: 0 }}>Reviewing partner — Uzbekistan pilot</dd>
          </div>
        </dl>
      </section>

      <section className="card" aria-labelledby="s-letter">
        <div className="panel-title">
          <h2 id="s-letter" style={{ fontSize: '1.05rem', margin: 0 }}>
            Verdict letters
          </h2>
          <StubTag>Demo — display only</StubTag>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="sig-name">Signature on letters</label>
          <input id="sig-name" className="input" defaultValue={`${state.session?.name} — Partner, Oqim`} />
          <p className="hint">Appears in the sign-off of every verdict letter you send.</p>
        </div>
      </section>

      <section className="card" aria-labelledby="s-notify">
        <div className="panel-title">
          <h2 id="s-notify" style={{ fontSize: '1.05rem', margin: 0 }}>
            Notifications
          </h2>
          <StubTag>Demo — display only</StubTag>
        </div>
        {[
          ['New submissions land in the pipeline', true],
          ['Daily digest of the New column', true],
          ['Founder replies to a sent verdict', false],
        ].map(([label, on]) => (
          <label key={label as string} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '6px 0' }}>
            <input type="checkbox" defaultChecked={on as boolean} style={{ width: 17, height: 17, accentColor: 'var(--brand)' }} />
            {label}
          </label>
        ))}
      </section>

      <section className="card" aria-labelledby="s-demo">
        <h2 id="s-demo" style={{ fontSize: '1.05rem' }}>
          Demo controls
        </h2>
        <p className="muted">
          Reset restores the seeded pipeline and clears the demo founder's submission and any decisions
          you've made.
        </p>
        {confirmReset ? (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                resetDemo()
                setConfirmReset(false)
                toast('Demo data reset to the seeded state.')
              }}
            >
              Yes, reset everything
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(true)}>
            Reset demo data
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
          Log out
        </button>
      </div>
    </div>
  )
}
