import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import type { Signal, Stage } from '../lib/types'
import { cx } from '../lib/format'
import { LOCALES, LOCALE_NAME, useLocale, type Locale } from '../i18n'
import { CheckIcon, ChevronDownIcon, SignalHighIcon, SignalLowIcon, SignalMediumIcon, SparkIcon, WaveIcon } from './icons'

/** Green/yellow/red signal — always color + icon + label together. */
export function SignalTag({ signal, overridden }: { signal: Signal; overridden?: boolean }) {
  const { t } = useLocale()
  const Icon = signal === 'high' ? SignalHighIcon : signal === 'medium' ? SignalMediumIcon : SignalLowIcon
  return (
    <span className={cx('tag', `tag-${signal}`)}>
      <Icon />
      {t.signal[signal]}
      {overridden && <span className="visually-hidden">{t.badges.signalOverriddenSr}</span>}
    </span>
  )
}

export function StageBadge({ stage }: { stage: Stage }) {
  const { t } = useLocale()
  return <span className="stage-badge">{t.stageBadge[stage]}</span>
}

export function Wordmark({ to = '/', sub }: { to?: string; sub?: string }) {
  const { t } = useLocale()
  return (
    <Link to={to} className="wordmark" aria-label={t.wordmarkAria}>
      <span className="mark-wave" aria-hidden="true">
        <WaveIcon />
      </span>
      bevosita
      {sub && <span className="wordmark-sub">&nbsp;{sub}</span>}
    </Link>
  )
}

/** Marks simulated AI output. The framing is a product principle, not decoration. */
export function AiBadge({ children }: { children?: string }) {
  const { t } = useLocale()
  return (
    <span className="ai-badge">
      <SparkIcon />
      {children ?? t.badges.aiDefault}
    </span>
  )
}

/** Marks stubbed/simulated actions so demo boundaries stay honest. */
export function StubTag({ children }: { children?: string }) {
  const { t } = useLocale()
  return <span className="stub-tag">{children ?? t.badges.stubDefault}</span>
}

/** Compact interface-locale menu, shared by public, auth, founder, and VC chrome. */
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useLocale()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const itemRefs = useRef<Record<Locale, HTMLButtonElement | null>>({ uz: null, ru: null })
  const menuId = useId()

  useEffect(() => {
    if (!open) return

    itemRefs.current[locale]?.focus()
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [locale, open])

  const closeAndFocusTrigger = () => {
    setOpen(false)
    triggerRef.current?.focus()
  }

  const choose = (nextLocale: Locale) => {
    setLocale(nextLocale)
    closeAndFocusTrigger()
  }

  const focusItem = (index: number) => itemRefs.current[LOCALES[(index + LOCALES.length) % LOCALES.length]]?.focus()

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = LOCALES.findIndex((item) => itemRefs.current[item] === document.activeElement)
    if (event.key === 'Escape') {
      event.preventDefault()
      closeAndFocusTrigger()
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      focusItem(index + 1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      focusItem(index - 1)
    } else if (event.key === 'Home') {
      event.preventDefault()
      focusItem(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      focusItem(LOCALES.length - 1)
    } else if (event.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div className="lang-switcher" ref={rootRef} onKeyDown={handleMenuKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className="language-trigger"
        aria-label={`${t.switcher.label}: ${LOCALE_NAME[locale]}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            setOpen(true)
          }
        }}
      >
        <span aria-hidden="true">{locale.toUpperCase()}</span>
        <span className={cx('language-chevron', open && 'open')}>
          <ChevronDownIcon />
        </span>
      </button>

      {open && (
        <div id={menuId} className="language-menu" role="menu" aria-label={t.switcher.label}>
          {LOCALES.map((itemLocale) => (
            <button
              key={itemLocale}
              ref={(node) => {
                itemRefs.current[itemLocale] = node
              }}
              type="button"
              role="menuitemradio"
              lang={itemLocale}
              aria-checked={locale === itemLocale}
              tabIndex={-1}
              onClick={() => choose(itemLocale)}
            >
              <span>{LOCALE_NAME[itemLocale]}</span>
              {locale === itemLocale && <CheckIcon />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
