import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import '@fontsource-variable/fraunces'
import '@fontsource-variable/inter'
import './styles.css'
import { StoreProvider } from './lib/store'
import { ToastProvider } from './components/toast'
import { AppRoutes } from './App'

// HashRouter keeps deep links working on GitHub Pages (no server rewrites).
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <StoreProvider>
      <ToastProvider>
        <HashRouter>
          <AppRoutes />
        </HashRouter>
      </ToastProvider>
    </StoreProvider>
  </StrictMode>,
)
