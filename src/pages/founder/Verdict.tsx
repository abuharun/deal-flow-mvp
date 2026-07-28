import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import type { Lang } from '../../lib/types'
import { verdictTextFor } from '../../lib/verdictText'
import { LANG_LABEL } from '../../lib/compose'
import { useLocale } from '../../i18n'
import { formatDate, cx } from '../../lib/format'

// The verdict body's language selector — a separate axis from the interface
// locale, because the English original is a product guarantee.
const LANGS: Lang[] = ['uz', 'ru', 'en']

export default function FounderVerdict() {
  const { founderStartup } = useStore()
  const { locale, t } = useLocale()
  const [params, setParams] = useSearchParams()

  if (!founderStartup?.verdict?.sentAt) return <Navigate to="/apply" replace />
  const verdict = founderStartup.verdict

  const requested = params.get('lang') as Lang | null
  const lang: Lang = requested && LANGS.includes(requested) ? requested : verdict.localLang
  const text = verdictTextFor(founderStartup, lang)

  return (
    <article aria-labelledby="verdict-heading">
      <p className="status-chip" style={{ color: 'var(--green-ink)' }}>
        {t.verdict.decisionChip(t.decision[verdict.decision])}
      </p>
      <h1 id="verdict-heading" style={{ marginTop: 14 }}>
        {t.verdict.heading(founderStartup.name)}
      </h1>
      <p className="muted">{t.verdict.reviewedLine(formatDate(verdict.sentAt!, locale))}</p>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', margin: '18px 0' }}>
        <div className="lang-toggle" role="group" aria-label={t.verdict.langToggleAria}>
          {LANGS.map((l) => (
            <button
              key={l}
              type="button"
              lang={l}
              aria-pressed={lang === l}
              onClick={() => setParams({ lang: l })}
            >
              {LANG_LABEL[l]}
            </button>
          ))}
        </div>
        <Link to={`/apply/verdict/letter.pdf?lang=${lang}`} className="btn btn-secondary btn-sm">
          {t.verdict.downloadLetter}
        </Link>
      </div>

      <div className={cx('card')} lang={lang}>
        <div className="verdict-draft">{text}</div>
      </div>

      {lang !== 'en' && (
        <p className="faint" style={{ marginTop: 12 }}>
          {t.verdict.enAlways}{' '}
          <button
            type="button"
            className="btn btn-quiet btn-sm"
            style={{ display: 'inline-flex' }}
            onClick={() => setParams({ lang: 'en' })}
          >
            {t.verdict.enView}
          </button>
        </p>
      )}

      <hr className="divider" />
      <p className="muted" style={{ maxWidth: 560 }}>
        {t.verdict.questions(<Link to="/apply">{t.verdict.backToStartup}</Link>)}
      </p>
    </article>
  )
}
