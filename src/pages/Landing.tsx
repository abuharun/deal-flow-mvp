import { Link } from 'react-router-dom'
import { Wordmark } from '../components/ui'
import { CheckIcon } from '../components/icons'

export default function Landing() {
  return (
    <>
      <header className="landing-header">
        <Wordmark />
        <nav aria-label="Account" style={{ display: 'flex', gap: 10 }}>
          <Link to="/login" className="btn btn-quiet">
            Log in
          </Link>
          <Link to="/signup" className="btn btn-primary">
            Get started
          </Link>
        </nav>
      </header>

      <main className="landing-main">
        <section className="hero">
          <h1>
            An honest verdict for your startup.
            <br />
            Real signal for real capital.
          </h1>
          <p className="lede">
            Oqim connects founders in Uzbekistan with the standards of US venture capital. Submit your
            startup, get a truthful, human-reviewed verdict — and if it's fundable, a real path forward.
          </p>
          <div className="hero-actions">
            <Link to="/signup" className="btn btn-primary btn-lg">
              Submit your startup
            </Link>
            <Link to="/login" className="btn btn-secondary btn-lg">
              I review deals
            </Link>
          </div>
        </section>

        <section aria-labelledby="how-heading">
          <h2 id="how-heading">How it works</h2>
          <div className="landing-grid">
            <article className="card">
              <h3>1 · You submit</h3>
              <p className="muted">
                A structured six-step submission — problem, product, market, traction, team, ask. Save
                and resume anytime, built for a phone with a spotty connection.
              </p>
            </article>
            <article className="card">
              <h3>2 · We make you legible</h3>
              <p className="muted">
                AI standardizes your story into the format investors actually read, and suggests where
                you stand. It ranks attention — it never decides.
              </p>
            </article>
            <article className="card">
              <h3>3 · A partner decides</h3>
              <p className="muted">
                A real venture partner reviews your submission against your raw words, verifies your
                claims, and writes you an honest verdict — in your own language, with the reason.
              </p>
            </article>
          </div>
        </section>

        <section aria-labelledby="principles-heading" style={{ marginTop: 56 }}>
          <h2 id="principles-heading">What we promise</h2>
          <div className="landing-grid">
            <article className="card">
              <h3>Trust over automation</h3>
              <p className="muted">
                Every verdict is reviewed, edited, and sent by a human partner. The AI drafts; it never
                speaks to you unsupervised.
              </p>
            </article>
            <article className="card">
              <h3>Honest over flattering</h3>
              <p className="muted">
                A "no" with a real reason is worth more than a polite silence. If the answer is not yet,
                we tell you what would change it.
              </p>
            </article>
            <article className="card">
              <h3>A real path to US capital</h3>
              <p className="muted">
                Startups that clear the bar are advanced person-to-person to partners in the United
                States. No spray-and-pray, no cold lists.
              </p>
            </article>
          </div>
        </section>

        <section className="card" style={{ marginTop: 56, background: 'var(--brand-wash)' }}>
          <h2 style={{ marginBottom: 6 }}>For the founder who wants the truth</h2>
          <p className="muted" style={{ maxWidth: 640 }}>
            The validation fee buys you what no one else will give you: a serious review and a straight
            answer. Fundable by global standards, promising but early, or better built as a local
            business — you'll know, and you'll know why.
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: '14px 0 18px', display: 'grid', gap: 8 }}>
            {[
              'A structured review by a working venture partner',
              'A written verdict in Uzbek, Russian, or English',
              'An official verdict letter you can keep',
            ].map((t) => (
              <li key={t} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ color: 'var(--green-ink)' }}>
                  <CheckIcon />
                </span>
                {t}
              </li>
            ))}
          </ul>
          <Link to="/signup" className="btn btn-primary">
            Start your submission
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <span>Oqim — Tashkent · Austin. Product demo; no real submissions are processed.</span>
        <span>© 2026 Oqim</span>
      </footer>
    </>
  )
}
