import { Link } from 'react-router-dom'
import type { Signal, Stage } from '../lib/types'
import { cx } from '../lib/format'
import { LOCALES, LOCALE_NAME, useLocale } from '../i18n'
import { SignalHighIcon, SignalLowIcon, SignalMediumIcon, SparkIcon, WaveIcon } from './icons'

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

/**
 * Interface language switcher: O‘zbekcha / Русский. Plain buttons in a
 * labeled group — keyboard-operable by nature, `aria-pressed` marks the
 * active language, and the choice persists via LocaleProvider.
 */
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useLocale()
  return (
    <div className="lang-toggle lang-switcher" role="group" aria-label={t.switcher.label}>
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          lang={l}
          aria-pressed={locale === l}
          onClick={() => setLocale(l)}
        >
          {LOCALE_NAME[l]}
        </button>
      ))}
    </div>
  )
}
