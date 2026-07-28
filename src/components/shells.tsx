import { useEffect } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useStore } from '../lib/store'
import type { Role } from '../lib/types'
import { Wordmark } from './ui'
import { BoardIcon, ListIcon, PersonIcon } from './icons'

/** Auth guard: requires a session with the given role, else sends to login. */
export function RequireRole({ role }: { role: Role }) {
  const { state } = useStore()
  if (!state.session) return <Navigate to="/login" replace />
  if (state.session.role !== role) {
    return <Navigate to={state.session.role === 'founder' ? '/apply' : '/app'} replace />
  }
  return <Outlet />
}

export function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo?.(0, 0)
  }, [pathname])
  return null
}

function LogoutButton() {
  const { logout } = useStore()
  const navigate = useNavigate()
  return (
    <button
      type="button"
      className="btn btn-quiet btn-sm"
      onClick={() => {
        logout()
        navigate('/')
      }}
    >
      Log out
    </button>
  )
}

/** Founder chrome: nearly nav-free by design — a linear flow, not a place to browse. */
export function FounderShell() {
  const { state } = useStore()
  return (
    <div className="founder-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="founder-header">
        <Wordmark to="/apply" sub="for founders" />
        <nav aria-label="Account" className="vc-utility">
          <NavLink to="/apply/account" className="btn btn-quiet btn-sm">
            <PersonIcon size={15} /> {state.session?.name.split(' ')[0]}
          </NavLink>
          <LogoutButton />
        </nav>
      </header>
      <main id="main" className="founder-main">
        <Outlet />
      </main>
    </div>
  )
}

/** VC chrome: two-item primary nav, desktop-first, bottom tabs on mobile. */
export function VcShell() {
  const navClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')
  return (
    <div className="vc-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="vc-header">
        <Wordmark to="/app" sub="partner" />
        <nav className="vc-nav" aria-label="Primary">
          <NavLink to="/app" end className={navClass}>
            Pipeline
          </NavLink>
          <NavLink to="/app/startups" className={navClass}>
            Startups
          </NavLink>
        </nav>
        <div className="vc-utility">
          <NavLink to="/app/settings" className="btn btn-quiet btn-sm">
            Settings
          </NavLink>
          <LogoutButton />
        </div>
      </header>
      <main id="main" className="vc-main">
        <Outlet />
      </main>
      <nav className="mobile-tabbar" aria-label="Primary">
        <NavLink to="/app" end className={navClass}>
          <BoardIcon /> Pipeline
        </NavLink>
        <NavLink to="/app/startups" className={navClass}>
          <ListIcon /> Startups
        </NavLink>
        <NavLink to="/app/settings" className={navClass}>
          <PersonIcon /> Account
        </NavLink>
      </nav>
    </div>
  )
}
