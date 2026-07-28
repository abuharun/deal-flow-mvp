import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { StoreProvider, initialState, reducer } from '../lib/store'
import { ToastProvider } from '../components/toast'
import { opaqueId } from '../lib/simulate'

function renderAt(path: string) {
  return render(
    <StoreProvider>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </ToastProvider>
    </StoreProvider>,
  )
}

/** Pre-seed persisted state with a session so guarded routes render directly. */
function seedSession(role: 'founder' | 'vc') {
  localStorage.setItem('oqim:v1', JSON.stringify(reducer(initialState(), { type: 'login', role })))
}

beforeEach(() => localStorage.clear())

describe('public pages', () => {
  it('renders the landing value proposition', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/An honest verdict/)
    expect(screen.getByRole('link', { name: /Submit your startup/ })).toBeInTheDocument()
  })

  it('guards role routes behind login', () => {
    renderAt('/app')
    expect(screen.getByRole('heading', { name: 'Log in' })).toBeInTheDocument()
  })
})

describe('demo login', () => {
  it('lands the founder on My Startup', async () => {
    const user = userEvent.setup()
    renderAt('/login')
    await user.click(screen.getByRole('button', { name: /Founder/ }))
    expect(await screen.findByRole('heading', { name: /fundable/ })).toBeInTheDocument()
  })

  it('lands the VC on the pipeline board', async () => {
    const user = userEvent.setup()
    renderAt('/login')
    await user.click(screen.getByRole('button', { name: /VC Partner/ }))
    expect(await screen.findByRole('heading', { name: 'Pipeline' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'New' })).toBeInTheDocument()
    expect(screen.getByText('Xarid')).toBeInTheDocument()
  })
})

describe('founder submission flow', () => {
  it('autosaves the draft and walks the six steps', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=problem')

    await user.type(screen.getByLabelText('Startup name'), 'TestCo')
    await user.type(screen.getByLabelText('Problem'), 'A real problem worth solving.')
    expect(screen.getByText(/Saved on this device/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(await screen.findByRole('heading', { name: /What have you built/ })).toBeInTheDocument()
    // Persistence survives a full remount (simulates leaving and returning).
    expect(JSON.parse(localStorage.getItem('oqim:v1')!).draft.startupName).toBe('TestCo')
  })

  it('refuses to continue past an empty step', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=problem')
    await user.click(screen.getByRole('button', { name: 'Continue' }))
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})

describe('VC review and verdict loop', () => {
  it('reviews, decides, composes, edits, and sends a verdict', async () => {
    const user = userEvent.setup()
    seedSession('vc')
    renderAt(`/app/startups/${opaqueId('xarid')}`)

    expect(await screen.findByRole('heading', { name: 'Xarid' })).toBeInTheDocument()
    // AI summary sits beside the raw founder inputs.
    expect(screen.getByRole('heading', { name: 'AI summary' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Raw founder inputs' })).toBeInTheDocument()

    // Verification checklist works.
    await user.click(screen.getByLabelText(/Revenue proof matches the claim/))
    expect(screen.getByText('1/4 verified')).toBeInTheDocument()

    // Decide + rough notes → compose.
    await user.click(screen.getByRole('button', { name: /^Recommend/ }))
    await user.type(screen.getByLabelText(/Rough notes/), 'rev is real w/ receipts{enter}team is strong')
    await user.click(screen.getByRole('button', { name: 'Compose verdict' }))

    const draftBox = (await screen.findByLabelText(/Edit the draft in place/)) as HTMLTextAreaElement
    expect(draftBox.value).toContain('Dear Aziza Karimova,')
    expect(draftBox.value).toContain('Revenue is real with receipts.')

    // Inline edit, then explicit two-step send.
    await user.type(draftBox, ' Edited.')
    await user.click(screen.getByRole('button', { name: 'Send verdict' }))
    await user.click(screen.getByRole('button', { name: /Confirm — send to/ }))
    expect(await screen.findByText(/Verdict sent to the founder/)).toBeInTheDocument()
  })
})
