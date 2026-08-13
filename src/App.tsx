import { Route, Routes, Link } from 'react-router-dom'
import { useLocale } from './i18n'
import { RequireRole as RequireDemoRole, FounderShell, VcShell, ScrollToTop } from './components/shells'
import Landing from './pages/Landing'
import { DemoEntry, Signup, Reset } from './pages/auth'
import Login from './auth/pages/Login'
import { RequireRole, FounderWorkspaceShell, VcWorkspaceShell } from './workspace/shell'
import StartupList from './workspace/founder/StartupList'
import StartupDetail from './workspace/founder/StartupDetail'
import ApprovedList from './workspace/vc/ApprovedList'
import Dossier from './workspace/vc/Dossier'
import FounderHome from './pages/founder/Home'
import Submit from './pages/founder/Submit'
import Pay from './pages/founder/Pay'
import FounderVerdict from './pages/founder/Verdict'
import Letter from './pages/founder/Letter'
import FounderAccount from './pages/founder/Account'
import Board from './pages/vc/Board'
import DemoStartupsList from './pages/vc/StartupsList'
import DemoStartupDetail from './pages/vc/StartupDetail'
import Settings from './pages/vc/Settings'

function NotFound() {
  const { t } = useLocale()
  return (
    <div className="auth-wrap">
      <div className="card" style={{ textAlign: 'center', maxWidth: 380 }}>
        <h1 style={{ fontSize: '1.4rem' }}>{t.notFound.title}</h1>
        <p className="muted">{t.notFound.body}</p>
        <Link to="/" className="btn btn-primary">
          {t.notFound.home}
        </Link>
      </div>
    </div>
  )
}

/**
 * Route tree, router-agnostic so tests can mount it in a MemoryRouter.
 *
 * Two surfaces live here, deliberately kept apart:
 * - The PRODUCT (`/login`, `/founder`, `/investor`) talks to the real API and
 *   is guarded by the server-issued session.
 * - The simulated DEMO (`/demo`, `/apply`, `/app`) keeps the older
 *   local-only prototype reachable. Nothing under `/demo` touches the API,
 *   and nothing outside it uses seeded data.
 */
export function AppRoutes() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />

        {/* Real, backend-backed founder workspace. */}
        <Route path="/founder" element={<RequireRole role="founder" />}>
          <Route element={<FounderWorkspaceShell />}>
            <Route index element={<StartupList />} />
            <Route path=":startupId" element={<StartupDetail />} />
          </Route>
        </Route>

        {/* Real, backend-backed investor workspace (read-only by contract). */}
        <Route path="/investor" element={<RequireRole role="vc" />}>
          <Route element={<VcWorkspaceShell />}>
            <Route index element={<ApprovedList />} />
            <Route path=":startupId" element={<Dossier />} />
          </Route>
        </Route>

        {/* Simulated demo — no API, clearly labelled in its own copy. */}
        <Route path="/demo" element={<DemoEntry />} />
        <Route path="/demo/signup" element={<Signup />} />
        <Route path="/demo/reset" element={<Reset />} />

        <Route path="/apply" element={<RequireDemoRole role="founder" />}>
          <Route element={<FounderShell />}>
            <Route index element={<FounderHome />} />
            <Route path="submit" element={<Submit />} />
            <Route path="submit/pay" element={<Pay />} />
            <Route path="verdict" element={<FounderVerdict />} />
            <Route path="account" element={<FounderAccount />} />
          </Route>
          {/* Letter renders without app chrome so print output is clean. */}
          <Route path="verdict/letter.pdf" element={<Letter />} />
        </Route>

        <Route path="/app" element={<RequireDemoRole role="vc" />}>
          <Route element={<VcShell />}>
            <Route index element={<Board />} />
            <Route path="startups" element={<DemoStartupsList />} />
            <Route path="startups/:id" element={<DemoStartupDetail />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  )
}
