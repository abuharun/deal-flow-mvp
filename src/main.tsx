import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import '@fontsource-variable/fraunces'
import '@fontsource-variable/inter'
import './styles.css'
import { StoreProvider } from './lib/store'
import { LocaleProvider } from './i18n'
import { ToastProvider } from './components/toast'
import { AuthProvider } from './auth/session'
import { AppRoutes } from './App'

// AuthProvider wraps everything: it asks the API (via the HttpOnly refresh
// cookie) whether a real session exists before any guarded route renders.
// StoreProvider stays alongside it, serving only the simulated /demo surface.
// HashRouter keeps deep links working on GitHub Pages (no server rewrites).
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LocaleProvider>
      <AuthProvider>
        <StoreProvider>
          <ToastProvider>
            <HashRouter>
              <AppRoutes />
            </HashRouter>
          </ToastProvider>
        </StoreProvider>
      </AuthProvider>
    </LocaleProvider>
  </StrictMode>,
)
