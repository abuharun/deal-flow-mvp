/**
 * Chrome and route guards for the backend-connected workspaces.
 *
 * The guard is a UX affordance, not a permission: it decides which chrome to
 * render from the role in the access token, while every actual authorization
 * decision stays server-side (backend/app/deps.py re-reads the user's role
 * from the database on every single request).
 */

import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/session'
import type { Role } from '../api/types'
import { useLocale } from '../i18n'
import { LanguageSwitcher, Wordmark } from '../components/ui'
import { ListIcon, PersonIcon } from '../components/icons'
import { LoadingPanel } from './states'

/** Where each role's workspace lives. */
export const HOME_PATH: Record<Role, string> = { founder: '/founder', vc: '/investor' }

export function RequireRole({ role }: { role: Role }) {
  const { status, role: actual } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="auth-wrap">
        <LoadingPanel />
      </div>
    )
  }
  // `from` lets the login page return the user to the page they asked for.
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (actual !== role) return <Navigate to={HOME_PATH[actual ?? 'founder']} replace />
  return <Outlet />
}

function SignOutButton() {
  const { signOut } = useAuth()
  const { t } = useLocale()
  const navigate = useNavigate()
  return (
    <button
      type="button"
      className="btn btn-quiet btn-sm"
      onClick={() => {
        // Leave the guarded area first: the moment the session clears, the
        // role guard would bounce this tab to /login and swallow the
        // navigation to the public landing.
        navigate('/')
        void signOut()
      }}
    >
      {t.common.logout}
    </button>
  )
}

/** The signed-in user's own name, or nothing at all — never a placeholder identity. */
function AccountLabel() {
  const { user } = useAuth()
  const { t } = useLocale()
  return (
    <span className="account-label">
      <PersonIcon size={15} /> {user ? user.full_name.split(' ')[0] : t.work.accountAria}
    </span>
  )
}

export function FounderWorkspaceShell() {
  const { t } = useLocale()
  return (
    <div className="founder-shell">
      <a className="skip-link" href="#main">
        {t.shell.skipToMain}
      </a>
      <header className="founder-header">
        <Wordmark to="/founder" sub={t.work.founderSub} />
        <nav aria-label={t.work.accountAria} className="vc-utility">
          <LanguageSwitcher />
          <AccountLabel />
          <SignOutButton />
        </nav>
      </header>
      <main id="main" className="founder-main">
        <Outlet />
      </main>
    </div>
  )
}

export function VcWorkspaceShell() {
  const { t } = useLocale()
  const navClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'active' : '')
  return (
    <div className="vc-shell">
      <a className="skip-link" href="#main">
        {t.shell.skipToMain}
      </a>
      <header className="vc-header">
        <Wordmark to="/investor" sub={t.work.vcSub} />
        <nav className="vc-nav" aria-label={t.shell.mainNavAria}>
          <NavLink to="/investor" end className={navClass}>
            {t.work.navPortfolio}
          </NavLink>
        </nav>
        <div className="vc-utility">
          <LanguageSwitcher />
          <AccountLabel />
          <SignOutButton />
        </div>
      </header>
      <main id="main" className="vc-main">
        <Outlet />
      </main>
      <nav className="mobile-tabbar" aria-label={t.shell.mainNavAria}>
        <NavLink to="/investor" end className={navClass}>
          <ListIcon /> {t.work.navPortfolio}
        </NavLink>
      </nav>
    </div>
  )
}
