import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useStore } from '../lib/store'
import { Wordmark } from '../components/ui'
import { FOUNDER_EMAIL, FOUNDER_NAME, VC_EMAIL, VC_NAME } from '../lib/seed'
import type { Role } from '../lib/types'

function AuthFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <div style={{ marginBottom: 18 }}>
          <Wordmark />
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
  const navigate = useNavigate()
  const enter = (role: Role) => {
    login(role)
    navigate(role === 'founder' ? '/apply' : '/app')
  }
  return (
    <div className="demo-roles" role="group" aria-label="Demo accounts">
      <button type="button" className="demo-role-btn" onClick={() => enter('founder')}>
        <span className="demo-avatar" aria-hidden="true">
          DE
        </span>
        <span>
          <strong>{FOUNDER_NAME}</strong> — Founder
          <br />
          <span className="faint">{FOUNDER_EMAIL} · submits a startup</span>
        </span>
      </button>
      <button type="button" className="demo-role-btn" onClick={() => enter('vc')}>
        <span className="demo-avatar" aria-hidden="true">
          LM
        </span>
        <span>
          <strong>{VC_NAME}</strong> — VC Partner
          <br />
          <span className="faint">{VC_EMAIL} · works the pipeline</span>
        </span>
      </button>
    </div>
  )
}

export function Login() {
  const { login } = useStore()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const role: Role = email.trim().toLowerCase() === VC_EMAIL ? 'vc' : 'founder'
    login(role)
    navigate(role === 'founder' ? '/apply' : '/app')
  }

  return (
    <AuthFrame title="Log in">
      <p className="demo-note" style={{ marginBottom: 16 }}>
        This is a product demo — any password works. Fastest path: pick a demo account below.
      </p>
      <DemoRoleChooser />
      <hr className="divider" />
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            className="input"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Password</label>
          <input id="login-password" className="input" type="password" autoComplete="current-password" required />
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          Log in
        </button>
      </form>
      <p className="faint" style={{ marginTop: 14 }}>
        <Link to="/reset">Forgot password?</Link> · New here? <Link to="/signup">Sign up</Link>
      </p>
    </AuthFrame>
  )
}

export function Signup() {
  const { login } = useStore()
  const navigate = useNavigate()

  const submit = (e: FormEvent) => {
    e.preventDefault()
    login('founder')
    navigate('/apply')
  }

  return (
    <AuthFrame title="Create your account">
      <p className="muted">Founders sign up here. Investor access is by invitation.</p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="su-name">Full name</label>
          <input id="su-name" className="input" autoComplete="name" required placeholder="Dilshod Ergashev" />
        </div>
        <div className="field">
          <label htmlFor="su-email">Email</label>
          <input id="su-email" className="input" type="email" autoComplete="email" required placeholder="you@example.com" />
        </div>
        <div className="field">
          <label htmlFor="su-password">Password</label>
          <input id="su-password" className="input" type="password" autoComplete="new-password" required minLength={8} />
          <p className="hint">At least 8 characters.</p>
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          Sign up
        </button>
      </form>
      <p className="demo-note" style={{ marginTop: 16 }}>
        Demo: signing up logs you in as the demo founder, {FOUNDER_NAME}.
      </p>
      <p className="faint" style={{ marginTop: 14 }}>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </AuthFrame>
  )
}

export function Reset() {
  const [sent, setSent] = useState(false)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setSent(true)
  }

  return (
    <AuthFrame title="Reset your password">
      {sent ? (
        <>
          <div className="sent-banner" role="status">
            Reset link sent (simulated) — check your inbox.
          </div>
          <p className="muted" style={{ marginTop: 14 }}>
            In this demo no email is actually sent. <Link to="/login">Back to log in</Link>.
          </p>
        </>
      ) : (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="rs-email">Email</label>
            <input id="rs-email" className="input" type="email" autoComplete="email" required placeholder="you@example.com" />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
            Send reset link
          </button>
          <p className="faint" style={{ marginTop: 14 }}>
            Remembered it? <Link to="/login">Log in</Link>
          </p>
        </form>
      )}
    </AuthFrame>
  )
}
