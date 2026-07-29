import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LocaleProvider } from '../i18n'
import { LanguageSwitcher, SignalTag } from './ui'

beforeEach(() => localStorage.clear())

describe('LanguageSwitcher', () => {
  function renderSwitcher() {
    return render(
      <LocaleProvider>
        <LanguageSwitcher />
        <button type="button">Outside</button>
      </LocaleProvider>,
    )
  }

  it('shows one compact menu trigger while closed', () => {
    renderSwitcher()

    const trigger = screen.getByRole('button', { name: /Interfeys tili.*O‘zbekcha/ })
    expect(trigger).toHaveTextContent('UZ')
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })

  it('opens from the keyboard and switches and persists the chosen locale', async () => {
    const user = userEvent.setup()
    renderSwitcher()

    await user.tab()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('button', { name: /Interfeys tili.*O‘zbekcha/ })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('menuitemradio', { name: 'O‘zbekcha' })).toHaveFocus()

    await user.keyboard('{ArrowDown}{Enter}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(localStorage.getItem('oqim:locale')).toBe('ru')
    expect(screen.getByRole('button', { name: /Язык интерфейса.*Русский/ })).toHaveTextContent('RU')
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    const user = userEvent.setup()
    renderSwitcher()
    const trigger = screen.getByRole('button', { name: /Interfeys tili.*O‘zbekcha/ })

    await user.click(trigger)
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveFocus()
  })

  it('closes when focus is clicked outside the switcher', async () => {
    const user = userEvent.setup()
    renderSwitcher()

    await user.click(screen.getByRole('button', { name: /Interfeys tili.*O‘zbekcha/ }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Outside' }))

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})

describe('SignalTag', () => {
  it.each([
    ['high', 'Kuchli signal'],
    ['medium', "O'rtacha signal"],
    ['low', 'Past signal'],
  ] as const)('pairs the %s color with a text label and an icon', (signal, label) => {
    const { container } = render(<SignalTag signal={signal} />)
    // Text label is always present — color is never the only signal.
    expect(screen.getByText(label)).toBeInTheDocument()
    // A distinct icon shape accompanies it.
    expect(container.querySelector('svg')).not.toBeNull()
    expect(container.querySelector(`.tag-${signal}`)).not.toBeNull()
  })

  it('announces a partner re-tag to screen readers', () => {
    render(<SignalTag signal="high" overridden />)
    expect(screen.getByText(/hamkor tomonidan qayta belgilangan/)).toBeInTheDocument()
  })
})
