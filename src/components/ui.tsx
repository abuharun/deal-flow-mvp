import { Link } from 'react-router-dom'
import type { Signal, Stage } from '../lib/types'
import { SIGNAL_LABEL, STAGE_LABEL, cx } from '../lib/format'
import { SignalHighIcon, SignalLowIcon, SignalMediumIcon, SparkIcon, WaveIcon } from './icons'

/** Green/yellow/red signal — always color + icon + label together. */
export function SignalTag({ signal, overridden }: { signal: Signal; overridden?: boolean }) {
  const Icon = signal === 'high' ? SignalHighIcon : signal === 'medium' ? SignalMediumIcon : SignalLowIcon
  return (
    <span className={cx('tag', `tag-${signal}`)}>
      <Icon />
      {SIGNAL_LABEL[signal]}
      {overridden && <span className="visually-hidden">(hamkor tomonidan qayta belgilangan)</span>}
    </span>
  )
}

export function StageBadge({ stage }: { stage: Stage }) {
  return <span className="stage-badge">{STAGE_LABEL[stage]}</span>
}

export function Wordmark({ to = '/', sub }: { to?: string; sub?: string }) {
  return (
    <Link to={to} className="wordmark" aria-label="Oqim — bosh sahifa">
      <span className="mark-wave" aria-hidden="true">
        <WaveIcon />
      </span>
      oqim
      {sub && <span className="wordmark-sub">&nbsp;{sub}</span>}
    </Link>
  )
}

/** Marks simulated AI output. The framing is a product principle, not decoration. */
export function AiBadge({ children = "Simulyatsiya qilingan AI · bu yo'l-yo'riq, xulosa emas" }: { children?: string }) {
  return (
    <span className="ai-badge">
      <SparkIcon />
      {children}
    </span>
  )
}

/** Marks stubbed/simulated actions so demo boundaries stay honest. */
export function StubTag({ children = 'Simulyatsiya' }: { children?: string }) {
  return <span className="stub-tag">{children}</span>
}
