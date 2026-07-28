import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import type { Lang } from '../../lib/types'
import { verdictTextFor } from '../../lib/verdictText'
import { useLocale } from '../../i18n'
import { formatDateLong } from '../../lib/format'
import { WaveIcon } from '../../components/icons'

/**
 * The official verdict letter, print-styled. "Download PDF" uses the browser's
 * print-to-PDF — an honest stand-in for server-side PDF generation in this demo.
 * The letter body follows the ?lang selector; the chrome follows the locale.
 */
export default function Letter() {
  const { founderStartup } = useStore()
  const { locale, t } = useLocale()
  const [params] = useSearchParams()

  if (!founderStartup?.verdict?.sentAt) return <Navigate to="/apply" replace />
  const verdict = founderStartup.verdict

  const requested = params.get('lang') as Lang | null
  const lang: Lang = requested && ['uz', 'ru', 'en'].includes(requested) ? requested : verdict.localLang
  const text = verdictTextFor(founderStartup, lang)

  return (
    <div className="letter-page">
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 18, flexWrap: 'wrap' }}>
        <Link to="/apply/verdict" className="btn btn-secondary btn-sm">
          {t.letter.backToVerdict}
        </Link>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => window.print()}>
          {t.letter.downloadPdf}
        </button>
      </div>

      <article className="letter-sheet" lang={lang} aria-label={t.letter.letterAria}>
        <div className="letter-brand">
          <span className="wordmark" style={{ fontSize: '1.2rem' }}>
            <span className="mark-wave" aria-hidden="true">
              <WaveIcon size={16} />
            </span>
            oqim
          </span>
          <span className="faint">{t.letter.letterheadLine(formatDateLong(verdict.sentAt!, locale))}</span>
        </div>
        <div className="letter-body">{text}</div>
        <hr className="divider" />
        <p className="faint">{t.letter.footer(founderStartup.id, founderStartup.name)}</p>
      </article>
    </div>
  )
}
