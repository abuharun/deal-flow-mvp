/**
 * The two prerequisites the founder grants by hand: the demo payment and the
 * AI/privacy consent.
 *
 * Payment is an honest stub and says so in its own copy — the founder picks
 * the simulated outcome, including the declined-card path, because pretending
 * a card was charged would be the one thing this screen must never do. A
 * successful demo payment is final (the API answers 409 to any attempt to
 * revert it), so the buttons disappear once it is paid.
 *
 * Consent is granted at the exact `current_version` the server just reported,
 * never a version this file knows: the backend rejects anything else with 422
 * CONSENT_VERSION_INVALID, which is precisely the protection that would be
 * lost by hardcoding one here.
 */

import type { ConsentSummaryResponse, PaymentResponse, PaymentStatus } from '../../api/types'
import { useLocale } from '../../i18n'
import { formatDate } from '../../lib/format'
import { ErrorPanel } from '../states'

export function PaymentPanel({
  payment,
  locked,
  busy,
  error,
  onPay,
}: {
  payment: PaymentResponse | null
  locked: boolean
  busy: boolean
  error: unknown
  onPay: (outcome: PaymentStatus) => void
}) {
  const { locale, t } = useLocale()
  const paid = payment?.status === 'paid'

  return (
    <div className="step-body">
      <p className="demo-note">{t.work.paymentDemoNotice}</p>
      {payment ? (
        <p>
          {paid ? t.work.paymentStatusPaid : t.work.paymentStatusFailed}
          {payment.paid_at && <span className="faint"> · {formatDate(payment.paid_at, locale)}</span>}
        </p>
      ) : (
        <p className="muted">{t.work.paymentNone}</p>
      )}
      {error !== null && error !== undefined && <ErrorPanel error={error} />}
      {!paid && !locked && (
        <div className="list-toolbar">
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => onPay('paid')}>
            {busy ? t.work.paymentBusy : t.work.paymentPay}
          </button>
          <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => onPay('failed')}>
            {t.work.paymentFail}
          </button>
        </div>
      )}
    </div>
  )
}

export function ConsentPanel({
  consents,
  locked,
  busy,
  error,
  onGrant,
}: {
  consents: ConsentSummaryResponse | null
  locked: boolean
  busy: boolean
  error: unknown
  onGrant: (textVersion: string) => void
}) {
  const { locale, t } = useLocale()
  if (!consents) return null
  const granted = consents.history.find((entry) => entry.text_version === consents.current_version)

  return (
    <div className="step-body">
      <p className="muted">{t.work.consentBody}</p>
      <p className="faint">{t.work.consentVersion(consents.current_version)}</p>
      {consents.granted ? (
        <p>
          {t.work.consentGranted}
          {granted && (
            <span className="faint">
              {' '}
              · {t.work.consentGrantedAt}: {formatDate(granted.granted_at, locale)}
            </span>
          )}
        </p>
      ) : (
        <>
          <p className="muted">{t.work.consentMissing}</p>
          {error !== null && error !== undefined && <ErrorPanel error={error} />}
          {!locked && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={busy}
              onClick={() => onGrant(consents.current_version)}
            >
              {busy ? t.work.consentBusy : t.work.consentGrant}
            </button>
          )}
        </>
      )}
    </div>
  )
}
