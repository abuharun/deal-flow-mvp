import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { useLocale } from '../../i18n'
import { localizePaymentLabel } from '../../lib/content'
import { formatDate } from '../../lib/format'
import { StubTag } from '../../components/ui'
import { useToast } from '../../components/toast'

export default function FounderAccount() {
  const { state, resetDemo, logout } = useStore()
  const { locale, t } = useLocale()
  const navigate = useNavigate()
  const toast = useToast()
  const [confirmReset, setConfirmReset] = useState(false)

  return (
    <div>
      <h1 style={{ fontSize: '1.6rem' }}>{t.account.title}</h1>

      <section className="card section-block" aria-labelledby="profile-heading">
        <h2 id="profile-heading" style={{ fontSize: '1.05rem' }}>
          {t.common.profile}
        </h2>
        <dl style={{ margin: 0, display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">{t.common.name}</dt>
            <dd style={{ margin: 0, fontWeight: 580 }}>{state.session?.name}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">{t.common.email}</dt>
            <dd style={{ margin: 0 }}>{state.session?.email}</dd>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <dt className="muted">{t.account.prefLang}</dt>
            <dd style={{ margin: 0 }}>{t.account.prefLangValue}</dd>
          </div>
        </dl>
      </section>

      <section className="card section-block" aria-labelledby="billing-heading">
        <div className="panel-title">
          <h2 id="billing-heading" style={{ fontSize: '1.05rem', margin: 0 }}>
            {t.account.billing}
          </h2>
          <StubTag>{t.account.billingStub}</StubTag>
        </div>
        {state.payments.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            {t.account.noPayments}
          </p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 8 }}>
            {state.payments.map((p) => (
              <li
                key={p.id}
                style={{ display: 'flex', justifyContent: 'space-between', gap: 12, borderTop: '1px solid var(--line)', paddingTop: 8 }}
              >
                <span>
                  {localizePaymentLabel(p.label, locale)}
                  <span className="faint" style={{ display: 'block' }}>
                    {formatDate(p.date, locale)}
                  </span>
                </span>
                <span className="num" style={{ color: p.status === 'failed' ? 'var(--red-ink)' : undefined }}>
                  {p.amount} {p.status === 'failed' ? t.account.failed : t.account.paid}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card section-block" aria-labelledby="demo-heading">
        <h2 id="demo-heading" style={{ fontSize: '1.05rem' }}>
          {t.account.demoHeading}
        </h2>
        <p className="muted">{t.account.demoBody}</p>
        {confirmReset ? (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                resetDemo()
                setConfirmReset(false)
                toast(t.account.toastReset)
              }}
            >
              {t.account.resetConfirm}
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(false)}>
              {t.common.cancel}
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn-secondary" onClick={() => setConfirmReset(true)}>
            {t.account.resetButton}
          </button>
        )}
      </section>

      <button
        type="button"
        className="btn btn-quiet"
        onClick={() => {
          logout()
          navigate('/')
        }}
      >
        {t.common.logout}
      </button>
    </div>
  )
}
