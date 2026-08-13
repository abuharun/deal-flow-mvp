/**
 * The real sign-in page: email + password against POST /auth/login.
 *
 * There is no demo shortcut here and no client-side role guessing — the role
 * that decides where the user lands comes from the access token the server
 * issued. Failures show the API's canonical reason (wrong credentials,
 * unverified email, rate limited), never a generic "something happened".
 */

import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../session'
import { useLocale } from '../../i18n'
import { LanguageSwitcher, Wordmark } from '../../components/ui'
import { HOME_PATH } from '../../workspace/shell'
import { useApiMessage } from '../../workspace/states'

export function AuthFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div className="auth-card-head">
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

export default function Login() {
  const { status, role, signIn } = useAuth()
  const { t } = useLocale()
  const navigate = useNavigate()
  const location = useLocation()
  const describe = useApiMessage()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  // Already signed in (e.g. the refresh cookie restored a session): never show
  // a login form over a live session.
  if (status === 'authenticated' && role) {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from ?? HOME_PATH[role]} replace />
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await signIn(email.trim(), password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from ?? HOME_PATH[user.role], { replace: true })
    } catch (cause) {
      setError(cause)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthFrame title={t.session.loginTitle}>
      <p className="muted">{t.session.loginIntro}</p>
      <form onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="login-email">{t.common.email}</label>
          <input
            id="login-email"
            className="input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder={t.session.emailPlaceholder}
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">{t.common.password}</label>
          <input
            id="login-password"
            className="input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error !== null && (
          <p className="error-text" role="alert">
            {describe(error)}
          </p>
        )}
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={busy}>
          {busy ? t.session.loginBusy : t.session.loginButton}
        </button>
      </form>
      <p className="faint" style={{ marginTop: 14 }}>
        {t.session.inviteOnlyNote} <Link to="/demo">{t.session.demoLink}</Link>
      </p>
    </AuthFrame>
  )
}
