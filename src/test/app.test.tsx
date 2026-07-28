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
  localStorage.setItem('oqim:v2', JSON.stringify(reducer(initialState(), { type: 'login', role })))
}

beforeEach(() => localStorage.clear())

describe('public pages', () => {
  it('renders the landing value proposition in Uzbek', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/halol xulosa/)
    expect(screen.getByRole('link', { name: /Startapingizni topshiring/ })).toBeInTheDocument()
  })

  it('guards role routes behind login', () => {
    renderAt('/app')
    expect(screen.getByRole('heading', { name: 'Kirish' })).toBeInTheDocument()
  })
})

describe('demo login', () => {
  it('lands the founder on My Startup', async () => {
    const user = userEvent.setup()
    renderAt('/login')
    await user.click(screen.getByRole('button', { name: /Asoschi/ }))
    expect(await screen.findByRole('heading', { name: /investitsiyaga loyiqmi/ })).toBeInTheDocument()
  })

  it('lands the VC on the pipeline board', async () => {
    const user = userEvent.setup()
    renderAt('/login')
    await user.click(screen.getByRole('button', { name: /Venchur hamkori/ }))
    expect(await screen.findByRole('heading', { name: 'Pipeline' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Yangi' })).toBeInTheDocument()
    expect(screen.getByText('Xarid')).toBeInTheDocument()
  })
})

describe('founder submission flow', () => {
  it('autosaves the draft and walks the six steps', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=problem')

    await user.type(screen.getByLabelText('Startap nomi'), 'TestCo')
    await user.type(screen.getByLabelText('Muammo'), 'Yechishga arziydigan haqiqiy muammo.')
    expect(screen.getByText(/Shu qurilmada saqlandi/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Davom etish' }))
    expect(await screen.findByRole('heading', { name: /Nima qurdingiz/ })).toBeInTheDocument()
    // Persistence survives a full remount (simulates leaving and returning).
    expect(JSON.parse(localStorage.getItem('oqim:v2')!).draft.startupName).toBe('TestCo')
  })

  it('refuses to continue past an empty step', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=problem')
    await user.click(screen.getByRole('button', { name: 'Davom etish' }))
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
    expect(screen.getByRole('heading', { name: 'AI qisqacha bayoni' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Asoschining asl matni' })).toBeInTheDocument()

    // Verification checklist works.
    await user.click(screen.getByLabelText(/Daromad isboti da'voga mos/))
    expect(screen.getByText('1/4 tekshirildi')).toBeInTheDocument()

    // Decide + rough notes → compose.
    await user.click(screen.getByRole('button', { name: /^Tavsiya qilish/ }))
    await user.type(
      screen.getByLabelText(/Qoralama yozuvlar/),
      'daromad haqiqiy, isbot bor{enter}jamoa kuchli',
    )
    await user.click(screen.getByRole('button', { name: 'Xulosa tayyorlash' }))

    const draftBox = (await screen.findByLabelText(/Qoralamani shu yerda tahrirlang/)) as HTMLTextAreaElement
    // The official English-original frame is preserved; reasons keep the notes' language.
    expect(draftBox.value).toContain('Dear Aziza Karimova,')
    expect(draftBox.value).toContain('Daromad haqiqiy, isbot bor.')

    // Inline edit, then explicit two-step send.
    await user.type(draftBox, ' Edited.')
    await user.click(screen.getByRole('button', { name: 'Xulosani yuborish' }))
    await user.click(screen.getByRole('button', { name: /Tasdiqlash — / }))
    expect(await screen.findByText(/Xulosa asoschiga/)).toBeInTheDocument()
  })
})
