import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// jsdom implements neither scrolling API; the app calls both (ScrollToTop,
// detail-page section navigation). No-op mocks keep tests faithful and quiet.
Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true })
Element.prototype.scrollIntoView = vi.fn()
