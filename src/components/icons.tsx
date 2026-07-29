/** Tiny inline icon set. Decorative by default (aria-hidden); labels live in text. */

interface IconProps {
  size?: number
}

export function WaveIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M2 12c2.2-4 4.2-4 6 0s3.8 4 6 0 3-3.4 4-2"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** High signal — upward arrow in a circle. */
export function SignalHighIcon({ size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <circle cx="7" cy="7" r="6.2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M7 10V4.5M4.6 6.8 7 4.4l2.4 2.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Medium signal — diamond with a dash. */
export function SignalMediumIcon({ size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="2.8" y="2.8" width="8.4" height="8.4" rx="1.5" transform="rotate(45 7 7)" stroke="currentColor" strokeWidth="1.4" />
      <path d="M4.8 7h4.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

/** Low signal — downward triangle. */
export function SignalLowIcon({ size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2.4 3.6h9.2L7 11.2 2.4 3.6Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}

export function CheckIcon({ size = 14 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2.5 7.5 5.5 10.5 11.5 3.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function SparkIcon({ size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M7 1.5 8.3 5.7 12.5 7 8.3 8.3 7 12.5 5.7 8.3 1.5 7 5.7 5.7 7 1.5Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function DocIcon({ size = 15 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M4 1.8h5.2L12.5 5v9.2H4V1.8Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M9 2v3.2h3.2" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  )
}

export function ClockIcon({ size = 28 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7v5.2l3.4 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

export function BoardIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <rect x="2" y="2.5" width="4" height="13" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="7.5" y="2.5" width="4" height="9" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
      <rect x="13" y="2.5" width="4" height="6" rx="1.2" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}

export function ListIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M6 4.5h9.5M6 9h9.5M6 13.5h9.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M2.5 4.5h.5M2.5 9h.5M2.5 13.5h.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function PersonIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="6" r="3.2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M3 15.5c.8-3 3.2-4.4 6-4.4s5.2 1.4 6 4.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

/** Chevron for menu triggers — points down closed, rotated open via CSS. */
export function ChevronDownIcon({ size = 13 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M3.2 5.4 7 9.2l3.8-3.8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
