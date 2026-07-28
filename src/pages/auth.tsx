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
    <div className="demo-roles" role="group" aria-label="Demo hisoblar">
      <button type="button" className="demo-role-btn" onClick={() => enter('founder')}>
        <span className="demo-avatar" aria-hidden="true">
          DE
        </span>
        <span>
          <strong>{FOUNDER_NAME}</strong> — Asoschi
          <br />
          <span className="faint">{FOUNDER_EMAIL} · startap topshiradi</span>
        </span>
      </button>
      <button type="button" className="demo-role-btn" onClick={() => enter('vc')}>
        <span className="demo-avatar" aria-hidden="true">
          LM
        </span>
        <span>
          <strong>{VC_NAME}</strong> — Venchur hamkori
          <br />
          <span className="faint">{VC_EMAIL} · pipeline bilan ishlaydi</span>
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
    <AuthFrame title="Kirish">
      <p className="demo-note" style={{ marginBottom: 16 }}>
        Bu mahsulot demosi — istalgan parol ishlaydi. Eng tez yo'l: quyidagi demo hisoblardan birini
        tanlang.
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
            placeholder="siz@misol.uz"
          />
        </div>
        <div className="field">
          <label htmlFor="login-password">Parol</label>
          <input id="login-password" className="input" type="password" autoComplete="current-password" required />
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          Kirish
        </button>
      </form>
      <p className="faint" style={{ marginTop: 14 }}>
        <Link to="/reset">Parolni unutdingizmi?</Link> · Yangimisiz?{' '}
        <Link to="/signup">Ro'yxatdan o'tish</Link>
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
    <AuthFrame title="Hisob yaratish">
      <p className="muted">Asoschilar shu yerda ro'yxatdan o'tadi. Investorlar faqat taklif orqali kiradi.</p>
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="su-name">To'liq ism</label>
          <input id="su-name" className="input" autoComplete="name" required placeholder="Dilshod Ergashev" />
        </div>
        <div className="field">
          <label htmlFor="su-email">Email</label>
          <input id="su-email" className="input" type="email" autoComplete="email" required placeholder="siz@misol.uz" />
        </div>
        <div className="field">
          <label htmlFor="su-password">Parol</label>
          <input id="su-password" className="input" type="password" autoComplete="new-password" required minLength={8} />
          <p className="hint">Kamida 8 ta belgi.</p>
        </div>
        <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
          Ro'yxatdan o'tish
        </button>
      </form>
      <p className="demo-note" style={{ marginTop: 16 }}>
        Demo: ro'yxatdan o'tsangiz, demo asoschi {FOUNDER_NAME} sifatida kirasiz.
      </p>
      <p className="faint" style={{ marginTop: 14 }}>
        Hisobingiz bormi? <Link to="/login">Kirish</Link>
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
    <AuthFrame title="Parolni tiklash">
      {sent ? (
        <>
          <div className="sent-banner" role="status">
            Tiklash havolasi yuborildi (simulyatsiya) — pochtangizni tekshiring.
          </div>
          <p className="muted" style={{ marginTop: 14 }}>
            Bu demoda hech qanday email aslida yuborilmaydi.{' '}
            <Link to="/login">Kirish sahifasiga qaytish</Link>.
          </p>
        </>
      ) : (
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="rs-email">Email</label>
            <input id="rs-email" className="input" type="email" autoComplete="email" required placeholder="siz@misol.uz" />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
            Tiklash havolasini yuborish
          </button>
          <p className="faint" style={{ marginTop: 14 }}>
            Esladingizmi? <Link to="/login">Kirish</Link>
          </p>
        </form>
      )}
    </AuthFrame>
  )
}
