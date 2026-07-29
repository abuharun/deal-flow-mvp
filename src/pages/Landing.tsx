import { Link } from 'react-router-dom'
import { useLocale } from '../i18n'
import { LanguageSwitcher, Wordmark } from '../components/ui'
import { CheckIcon } from '../components/icons'

/** Public assets respect the deploy base (GitHub Pages project path). */
const ASSET = (file: string) => `${import.meta.env.BASE_URL}assets/${file}`

export default function Landing() {
  const { t } = useLocale()
  const steps = [
    { num: '01', title: t.landing.how1Title, body: t.landing.how1Body },
    { num: '02', title: t.landing.how2Title, body: t.landing.how2Body },
    { num: '03', title: t.landing.how3Title, body: t.landing.how3Body },
  ]
  return (
    <>
      <div className="landing-topbar">
        <header className="landing-header">
          <Wordmark />
          <nav aria-label={t.landing.navAria} className="landing-nav">
            <button
              type="button"
              className="btn btn-quiet landing-assessment"
              onClick={() => document.getElementById('assessment')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            >
              {t.landing.assessment}
            </button>
            <Link to="/login" className="btn btn-quiet">
              {t.landing.login}
            </Link>
            <LanguageSwitcher />
            <Link to="/signup" className="btn btn-primary">
              {t.landing.start}
            </Link>
          </nav>
        </header>
      </div>

      <main className="landing-main">
        <section className="hero">
          <div className="hero-copy">
            <p className="hero-overline">{t.landing.badge}</p>
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
          </div>
          <figure className="hero-visual">
            <div className="hero-frame">
              <picture>
                <img
                  src={ASSET('bevosita-global-network.webp')}
                  alt={t.landing.heroAlt}
                  width={1823}
                  height={863}
                  loading="eager"
                  fetchPriority="high"
                  decoding="async"
                />
              </picture>
            </div>
            <figcaption className="hero-caption">{t.landing.heroCaption}</figcaption>
          </figure>
        </section>

        <section aria-labelledby="how-heading" className="flow-section">
          <p className="eyebrow">{t.landing.flowKicker}</p>
          <h2 id="how-heading">{t.landing.howHeading}</h2>
          <div className="flow-banner">
            <div className="flow-banner-copy">
              <h3>{t.landing.flowTitle}</h3>
              <p className="muted">{t.landing.flowBody}</p>
            </div>
            <picture className="flow-banner-media">
              <img
                src={ASSET('bevosita-deal-flow.webp')}
                alt={t.landing.flowAlt}
                width={1823}
                height={863}
                loading="lazy"
                decoding="async"
              />
            </picture>
          </div>
          <ol className="flow-steps">
            {steps.map((step) => (
              <li key={step.num}>
                <span className="step-num" aria-hidden="true">
                  {step.num}
                </span>
                <h3>{step.title}</h3>
                <p className="muted">{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="principles-heading" className="principles-section">
          <p className="eyebrow">{t.landing.promiseKicker}</p>
          <h2 id="principles-heading">{t.landing.promiseHeading}</h2>
          <div className="bento-grid">
            <article className="card bento-lead">
              <h3>{t.landing.p1Title}</h3>
              <p className="muted">{t.landing.p1Body}</p>
            </article>
            <article className="card bento-side">
              <h3>{t.landing.p2Title}</h3>
              <p className="muted">{t.landing.p2Body}</p>
            </article>
            <article className="card bento-side">
              <h3>{t.landing.p3Title}</h3>
              <p className="muted">{t.landing.p3Body}</p>
            </article>
          </div>
        </section>

        <section id="assessment" className="assessment-section" aria-labelledby="fee-heading">
          <h2 id="fee-heading">{t.landing.feeHeading}</h2>
          <p className="muted assessment-lede">{t.landing.feeBody}</p>
          <ul className="assessment-bullets">
            {t.landing.feeBullets.map((bullet) => (
              <li key={bullet}>
                <span className="assessment-check">
                  <CheckIcon />
                </span>
                {bullet}
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
