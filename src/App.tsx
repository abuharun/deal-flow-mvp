import { Route, Routes, Link } from 'react-router-dom'
import { useLocale } from './i18n'
import { RequireRole, FounderShell, VcShell, ScrollToTop } from './components/shells'
import Landing from './pages/Landing'
import { Login, Signup, Reset } from './pages/auth'
import FounderHome from './pages/founder/Home'
import Submit from './pages/founder/Submit'
import Pay from './pages/founder/Pay'
import FounderVerdict from './pages/founder/Verdict'
import Letter from './pages/founder/Letter'
import FounderAccount from './pages/founder/Account'
import Board from './pages/vc/Board'
import StartupsList from './pages/vc/StartupsList'
import StartupDetail from './pages/vc/StartupDetail'
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

/** Route tree, router-agnostic so tests can mount it in a MemoryRouter. */
export function AppRoutes() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/reset" element={<Reset />} />

        <Route path="/apply" element={<RequireRole role="founder" />}>
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

        <Route path="/app" element={<RequireRole role="vc" />}>
          <Route element={<VcShell />}>
            <Route index element={<Board />} />
            <Route path="startups" element={<StartupsList />} />
            <Route path="startups/:id" element={<StartupDetail />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  )
}
