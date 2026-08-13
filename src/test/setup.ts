import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// jsdom implements neither scrolling API; the app calls both (ScrollToTop,
// detail-page section navigation). No-op mocks keep tests faithful and quiet.
Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true })
Element.prototype.scrollIntoView = vi.fn()

// No test may reach a real network. The default behaves exactly like an
// unreachable API (the same TypeError the browser throws), so a component that
// forgets to stub fetch renders its error state instead of hanging or, worse,
// hitting a live backend. Tests that exercise the API stub `fetch` themselves.
globalThis.fetch = vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))) as unknown as typeof fetch
