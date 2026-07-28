import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStore } from '../lib/store'
import { useLocale } from '../i18n'
import { LanguageSwitcher, Wordmark } from '../components/ui'
import { FOUNDER_EMAIL, FOUNDER_NAME, VC_EMAIL, VC_NAME } from '../lib/seed'
import type { Role } from '../lib/types'

function AuthFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div style={{ marginBottom: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <Wordmark />
          <LanguageSwitcher />
        </div>
        <div className="card">
          <h1 style={{ fontSize: '1.5rem' }}>{title}</h1>
          {children}
        </div>
      </div>
    </div>
  )
}

function DemoRoleChooser() {
  const { login } = useStore()
  const { t } = useLocale()
  const navigate = useNavigate()
  const enter = (role: Role) => {
    login(role)
    navigate(role === 'founder' ? '/apply' : '/app')
  }
  return (
    <div className="demo-roles" role="group" aria-label={t.auth.demoRolesAria}>
      <button type="button" className="demo-role-btn" onClick={() => enter('founder')}>
        <span className="demo-avatar" aria-hidden="true">
          DE
        </span>
        <span>
          <strong>{FOUNDER_NAME}</strong> — {t.auth.founderRole}
          <br />
          <span className="faint">{t.auth.founderRoleSub(FOUNDER_EMAIL)}</span>
        </span>
      </button>
      <button type="button" className="demo-role-btn" onClick={() => enter('vc')}>
        <span className="demo-avatar" aria-hidden="true">
          LM
        </span>
        <span>
          <strong>{VC_NAME}</strong> — {t.auth.vcRole}
          <br />
          <span className="faint">{t.auth.vcRoleSub(VC_EMAIL)}</span>
        </span>
      </button>
    </div>
  )
}

export function Login() {
  const { login } = useStore()
  const { t } = useLocale()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const role: Role = email.trim().toLowerCase() === VC_EMAIL ? 'vc' : 'founder'
    login(role)
    navigate(role === 'founder' ? '/apply' : '/app')
  }

  return (
    <AuthFrame title={t.auth.loginTitle}>
      <p className="demo-note" style={{ marginBottom: 16 }}>
        {t.auth.loginDemoNote}
      </p>
      <DemoRoleChooser />
      <hr className="divider" />
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="login-email">{t.common.email}</label>
          <input
            id="login-email"
            className="input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t.auth.emailPlaceholder}
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">{t.common.password}</label>
          <input id="login-password" className="input" type="password" autoComplete="current-password" required />
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          {t.auth.loginButton}
        </button>
      </form>
      <p className="faint" style={{ marginTop: 14 }}>
        <Link to="/reset">{t.auth.forgot}</Link> · {t.auth.newHere}{' '}
        <Link to="/signup">{t.auth.signupLink}</Link>
      </p>
    </AuthFrame>
  )
}

export function Signup() {
  const { login } = useStore()
  const { t } = useLocale()
  const navigate = useNavigate()

  const submit = (e: FormEvent) => {
    e.preventDefault()
    login('founder')
    navigate('/apply')
  }

  return (
    <AuthFrame title={t.auth.signupTitle}>
      <p className="muted">{t.auth.signupIntro}</p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="su-name">{t.auth.fullName}</label>
          <input id="su-name" className="input" autoComplete="name" required placeholder={FOUNDER_NAME} />
        </div>
        <div className="field">
          <label htmlFor="su-email">{t.common.email}</label>
          <input id="su-email" className="input" type="email" autoComplete="email" required placeholder={t.auth.emailPlaceholder} />
        </div>
        <div className="field">
          <label htmlFor="su-password">{t.common.password}</label>
          <input id="su-password" className="input" type="password" autoComplete="new-password" required minLength={8} />
          <p className="hint">{t.auth.passwordHint}</p>
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          {t.auth.signupButton}
        </button>
      </form>
      <p className="demo-note" style={{ marginTop: 16 }}>
        {t.auth.signupDemoNote(FOUNDER_NAME)}
      </p>
      <p className="faint" style={{ marginTop: 14 }}>
        {t.auth.haveAccount} <Link to="/login">{t.auth.loginLink}</Link>
      </p>
    </AuthFrame>
  )
}

export function Reset() {
  const { t } = useLocale()
  const [sent, setSent] = useState(false)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setSent(true)
  }

  return (
    <AuthFrame title={t.auth.resetTitle}>
      {sent ? (
        <>
          <div className="sent-banner" role="status">
            {t.auth.resetSent}
          </div>
          <p className="muted" style={{ marginTop: 14 }}>
            {t.auth.resetNote(<Link to="/login">{t.auth.resetBackLink}</Link>)}
          </p>
        </>
      ) : (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="rs-email">{t.common.email}</label>
            <input id="rs-email" className="input" type="email" autoComplete="email" required placeholder={t.auth.emailPlaceholder} />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
            {t.auth.resetButton}
          </button>
          <p className="faint" style={{ marginTop: 14 }}>
            {t.auth.remembered} <Link to="/login">{t.auth.loginLink}</Link>
          </p>
        </form>
      )}
    </AuthFrame>
  )
}
