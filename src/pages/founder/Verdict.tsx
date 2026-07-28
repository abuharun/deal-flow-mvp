import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import type { Lang } from '../../lib/types'
import { verdictTextFor } from '../../lib/verdictText'
import { LANG_LABEL } from '../../lib/compose'
import { DECISION_LABEL, formatDate, cx } from '../../lib/format'

const LANGS: Lang[] = ['uz', 'ru', 'en']

export default function FounderVerdict() {
  const { founderStartup } = useStore()
  const [params, setParams] = useSearchParams()

  if (!founderStartup?.verdict?.sentAt) return <Navigate to="/apply" replace />
  const verdict = founderStartup.verdict

  const requested = params.get('lang') as Lang | null
  const lang: Lang = requested && LANGS.includes(requested) ? requested : verdict.localLang
  const text = verdictTextFor(founderStartup, lang)

  return (
    <article aria-labelledby="verdict-heading">
      <p className="status-chip" style={{ color: 'var(--green-ink)' }}>
        Decision: {DECISION_LABEL[verdict.decision]}
      </p>
      <h1 id="verdict-heading" style={{ marginTop: 14 }}>
        Your verdict for {founderStartup.name}
      </h1>
      <p className="muted">
        Reviewed and signed by the partner · sent {formatDate(verdict.sentAt!)}
      </p>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', margin: '18px 0' }}>
        <div className="lang-toggle" role="group" aria-label="Verdict language">
          {LANGS.map((l) => (
            <button
              key={l}
              type="button"
              aria-pressed={lang === l}
              onClick={() => setParams({ lang: l })}
            >
              {LANG_LABEL[l]}
            </button>
          ))}
        </div>
        <Link to={`/apply/verdict/letter.pdf?lang=${lang}`} className="btn btn-secondary btn-sm">
          Download official letter (PDF)
        </Link>
      </div>

      <div className={cx('card')} lang={lang}>
        <div className="verdict-draft">{text}</div>
      </div>

      {lang !== 'en' && (
        <p className="faint" style={{ marginTop: 12 }}>
          The English original is always available —{' '}
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            style={{ display: 'inline-flex' }}
            onClick={() => setParams({ lang: 'en' })}
          >
            view English original
          </button>
        </p>
      )}

      <hr className="divider" />
      <p className="muted" style={{ maxWidth: 560 }}>
        Questions about this decision? Reply from your account email and the partner will explain their
        thinking. <Link to="/apply">Back to My Startup</Link>
      </p>
    </article>
  )
}
