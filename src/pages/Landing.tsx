import { Link } from 'react-router-dom'
import { useLocale } from '../i18n'
import { LanguageSwitcher, Wordmark } from '../components/ui'
import { CheckIcon } from '../components/icons'

export default function Landing() {
  const { t } = useLocale()
  return (
    <>
      <header className="landing-header">
        <Wordmark />
        <nav aria-label={t.landing.navAria} style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <LanguageSwitcher />
          <Link to="/login" className="btn btn-quiet">
            {t.landing.login}
          </Link>
          <Link to="/signup" className="btn btn-primary">
            {t.landing.start}
          </Link>
        </nav>
      </header>

      <main className="landing-main">
        <section className="hero">
          <h1>
            {t.landing.hero1}
            <br />
            {t.landing.hero2}
          </h1>
          <p className="lede">{t.landing.lede}</p>
          <div className="hero-actions">
            <Link to="/signup" className="btn btn-primary btn-lg">
              {t.landing.ctaSubmit}
            </Link>
            <Link to="/login" className="btn btn-secondary btn-lg">
              {t.landing.ctaVc}
            </Link>
          </div>
        </section>

        <section aria-labelledby="how-heading">
          <h2 id="how-heading">{t.landing.howHeading}</h2>
          <div className="landing-grid">
            <article className="card">
              <h3>{t.landing.how1Title}</h3>
              <p className="muted">{t.landing.how1Body}</p>
            </article>
            <article className="card">
              <h3>{t.landing.how2Title}</h3>
              <p className="muted">{t.landing.how2Body}</p>
            </article>
            <article className="card">
              <h3>{t.landing.how3Title}</h3>
              <p className="muted">{t.landing.how3Body}</p>
            </article>
          </div>
        </section>

        <section aria-labelledby="principles-heading" style={{ marginTop: 56 }}>
          <h2 id="principles-heading">{t.landing.promiseHeading}</h2>
          <div className="landing-grid">
            <article className="card">
              <h3>{t.landing.p1Title}</h3>
              <p className="muted">{t.landing.p1Body}</p>
            </article>
            <article className="card">
              <h3>{t.landing.p2Title}</h3>
              <p className="muted">{t.landing.p2Body}</p>
            </article>
            <article className="card">
              <h3>{t.landing.p3Title}</h3>
              <p className="muted">{t.landing.p3Body}</p>
            </article>
          </div>
        </section>

        <section className="card" style={{ marginTop: 56, background: 'var(--brand-wash)' }}>
          <h2 style={{ marginBottom: 6 }}>{t.landing.feeHeading}</h2>
          <p className="muted" style={{ maxWidth: 640 }}>
            {t.landing.feeBody}
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: '14px 0 18px', display: 'grid', gap: 8 }}>
            {t.landing.feeBullets.map((b) => (
              <li key={b} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ color: 'var(--green-ink)' }}>
                  <CheckIcon />
                </span>
                {b}
              </li>
            ))}
          </ul>
          <Link to="/signup" className="btn btn-primary">
            {t.landing.feeCta}
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <span>{t.landing.footerLine}</span>
        <span>{t.landing.footerCopyright}</span>
      </footer>
    </>
  )
}
