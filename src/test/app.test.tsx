import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { StoreProvider, initialState, reducer } from '../lib/store'
import { ToastProvider } from '../components/toast'
import { opaqueId } from '../lib/simulate'
import { LocaleProvider } from '../i18n'

function renderAt(path: string) {
  return render(
    <LocaleProvider>
      <StoreProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[path]}>
            <AppRoutes />
          </MemoryRouter>
        </ToastProvider>
      </StoreProvider>
    </LocaleProvider>,
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
    expect(screen.getByRole('link', { name: 'Bevosita — bosh sahifa' })).toHaveTextContent('bevosita')
    expect(screen.getByRole('link', { name: /Startapingizni topshiring/ })).toBeInTheDocument()
  })

  it('orders assessment, login, the single language trigger, and start in the landing header', () => {
    renderAt('/')
    const assessment = screen.getByRole('button', { name: 'Baholash' })
    const login = screen.getByRole('link', { name: 'Kirish' })
    const language = screen.getByRole('button', { name: /Interfeys tili.*O‘zbekcha/ })
    const start = screen.getByRole('link', { name: 'Boshlash' })
    expect(assessment).toHaveAttribute('type', 'button')
    expect(document.getElementById('assessment')).toBeInTheDocument()
    expect(assessment.nextElementSibling).toBe(login)
    expect(login.nextElementSibling).toContainElement(language)
    expect(login.nextElementSibling?.nextElementSibling).toBe(start)
    expect(language).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('guards role routes behind login', () => {
    renderAt('/app')
    expect(screen.getByRole('heading', { name: 'Kirish' })).toBeInTheDocument()
  })

  it('switches the whole interface to Russian and persists the choice', async () => {
    const user = userEvent.setup()
    const first = renderAt('/')

    await user.click(screen.getByRole('button', { name: /Interfeys tili.*O‘zbekcha/ }))
    await user.click(screen.getByRole('menuitemradio', { name: 'Русский' }))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Честное заключение')
    expect(document.documentElement).toHaveAttribute('lang', 'ru')
    expect(document.title).toBe('Bevosita — честный поток сделок')
    expect(screen.getByRole('button', { name: 'Оценка' })).toHaveAttribute('type', 'button')
    expect(localStorage.getItem('oqim:locale')).toBe('ru')

    first.unmount()
    renderAt('/login')
    expect(screen.getByRole('heading', { name: 'Вход' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Язык интерфейса.*Русский/ })).toHaveAttribute('aria-expanded', 'false')
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
  it('renders VC settings and seeded pipeline content in Russian', () => {
    localStorage.setItem('oqim:locale', 'ru')
    seedSession('vc')
    const view = renderAt('/app/settings')

    expect(screen.getByRole('heading', { name: 'Настройки' })).toBeInTheDocument()
    expect(screen.getByText('Рассматривающий партнёр — пилот в Узбекистане')).toBeInTheDocument()
    expect(screen.getByText('Когда в пайплайн поступают новые заявки')).toBeInTheDocument()

    view.unmount()
    renderAt('/app')
    expect(screen.getByText('B2B-маркетплейс снабжения для ресторанов и кафе')).toBeInTheDocument()
    expect(screen.getByText('$24.7k валовой / мес')).toBeInTheDocument()
  })

  it('renders the Russian archive, startup detail, seeded text, and dates', () => {
    localStorage.setItem('oqim:locale', 'ru')
    seedSession('vc')
    const archive = renderAt('/app/startups')

    expect(screen.getByRole('heading', { name: 'Стартапы' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Подан' })).toBeInTheDocument()
    expect(screen.getByText('27 июл. 2026')).toBeInTheDocument()
    expect(screen.getByText('B2B-маркетплейс снабжения для ресторанов и кафе')).toBeInTheDocument()

    archive.unmount()
    renderAt(`/app/startups/${opaqueId('xarid')}`)
    expect(screen.getByRole('heading', { name: 'Краткая сводка ИИ' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Исходный текст основателя' })).toBeInTheDocument()
    expect(screen.getAllByText(/^Рестораны Ташкента закупают овощи/)).toHaveLength(2)
    expect(screen.getByText(/подан:/)).toHaveTextContent('26 июл. 2026')
  })

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
