import { useEffect } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useStore } from '../lib/store'
import type { Role } from '../lib/types'
import { useLocale } from '../i18n'
import { LanguageSwitcher, Wordmark } from './ui'
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
  const { t } = useLocale()
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
      {t.common.logout}
    </button>
  )
}

/** Founder chrome: nearly nav-free by design — a linear flow, not a place to browse. */
export function FounderShell() {
  const { state } = useStore()
  const { t } = useLocale()
  return (
    <div className="founder-shell">
      <a className="skip-link" href="#main">
        {t.shell.skipToMain}
      </a>
      <header className="founder-header">
        <Wordmark to="/apply" sub={t.shell.founderSub} />
        <nav aria-label={t.shell.accountNavAria} className="vc-utility">
          <LanguageSwitcher />
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
  const { t } = useLocale()
  const navClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')
  return (
    <div className="vc-shell">
      <a className="skip-link" href="#main">
        {t.shell.skipToMain}
      </a>
      <header className="vc-header">
        <Wordmark to="/app" sub={t.shell.vcSub} />
        <nav className="vc-nav" aria-label={t.shell.mainNavAria}>
          <NavLink to="/app" end className={navClass}>
            {t.shell.pipeline}
          </NavLink>
          <NavLink to="/app/startups" className={navClass}>
            {t.shell.startups}
          </NavLink>
        </nav>
        <div className="vc-utility">
          <LanguageSwitcher />
          <NavLink to="/app/settings" className="btn btn-quiet btn-sm">
            {t.shell.settings}
          </NavLink>
          <LogoutButton />
        </div>
      </header>
      <main id="main" className="vc-main">
        <Outlet />
      </main>
      <nav className="mobile-tabbar" aria-label={t.shell.mainNavAria}>
        <NavLink to="/app" end className={navClass}>
          <BoardIcon /> {t.shell.pipeline}
        </NavLink>
        <NavLink to="/app/startups" className={navClass}>
          <ListIcon /> {t.shell.startups}
        </NavLink>
        <NavLink to="/app/settings" className={navClass}>
          <PersonIcon /> {t.shell.account}
        </NavLink>
      </nav>
    </div>
  )
}
