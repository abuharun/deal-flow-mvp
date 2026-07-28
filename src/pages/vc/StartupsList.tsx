import { Link, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import type { Signal, Stage, Startup } from '../../lib/types'
import { useLocale } from '../../i18n'
import { localizeStartup } from '../../lib/content'
import { SIGNAL_ORDER, STAGE_ORDER, formatDate } from '../../lib/format'
import { SignalTag, StageBadge } from '../../components/ui'

type SortKey = 'recent' | 'oldest' | 'signal' | 'name'

function matches(s: Startup, q: string): boolean {
  if (!q) return true
  const hay = [s.name, s.oneLiner, s.sector, s.founder.name, ...Object.values(s.summary)]
    .join(' ')
    .toLowerCase()
  return q
    .toLowerCase()
    .split(/\s+/)
    .every((term) => hay.includes(term))
}

export default function StartupsList() {
  const { state } = useStore()
  const { locale, t } = useLocale()
  const [params, setParams] = useSearchParams()

  const q = params.get('q') ?? ''
  const stage = params.get('stage') ?? ''
  const signal = params.get('signal') ?? ''
  const outcome = params.get('outcome') ?? ''
  const sort = (params.get('sort') as SortKey) || 'recent'

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  // Localize first so full-text search matches what the reviewer actually sees.
  let rows = state.startups
    .map((s) => localizeStartup(s, locale))
    .filter(
      (s) =>
        matches(s, q) &&
        (!stage || s.stage === (stage as Stage)) &&
        (!signal || s.signal === (signal as Signal)) &&
        (!outcome || (outcome === 'undecided' ? s.decision === null : s.decision === outcome)),
    )

  rows = [...rows].sort((a, b) => {
    switch (sort) {
      case 'name':
        return a.name.localeCompare(b.name)
      case 'signal':
        return SIGNAL_ORDER[a.signal] - SIGNAL_ORDER[b.signal] || b.submittedAt.localeCompare(a.submittedAt)
      case 'oldest':
        return a.submittedAt.localeCompare(b.submittedAt)
      default:
        return b.submittedAt.localeCompare(a.submittedAt)
    }
  })

  return (
    <div>
      <h1 style={{ fontSize: '1.5rem' }}>{t.list.title}</h1>
      <p className="muted" style={{ marginTop: -6 }}>
        {t.list.intro}
      </p>

      <div className="list-toolbar" role="search">
        <input
          type="search"
          className="input search"
          placeholder={t.list.searchPlaceholder}
          aria-label={t.list.searchAria}
          value={q}
          onChange={(e) => setParam('q', e.target.value)}
        />
        <label className="visually-hidden" htmlFor="filter-stage">
          {t.list.filterStage}
        </label>
        <select id="filter-stage" className="select" value={stage} onChange={(e) => setParam('stage', e.target.value)}>
          <option value="">{t.list.allStages}</option>
          {STAGE_ORDER.map((st) => (
            <option key={st} value={st}>
              {t.stage[st]}
            </option>
          ))}
        </select>
        <label className="visually-hidden" htmlFor="filter-signal">
          {t.list.filterSignal}
        </label>
        <select id="filter-signal" className="select" value={signal} onChange={(e) => setParam('signal', e.target.value)}>
          <option value="">{t.list.allSignals}</option>
          {(['high', 'medium', 'low'] as Signal[]).map((s) => (
            <option key={s} value={s}>
              {t.signal[s]}
            </option>
          ))}
        </select>
        <label className="visually-hidden" htmlFor="filter-outcome">
          {t.list.filterOutcome}
        </label>
        <select id="filter-outcome" className="select" value={outcome} onChange={(e) => setParam('outcome', e.target.value)}>
          <option value="">{t.list.allOutcomes}</option>
          <option value="recommend">{t.list.outcome.recommend}</option>
          <option value="advance">{t.list.outcome.advance}</option>
          <option value="pass">{t.list.outcome.pass}</option>
          <option value="undecided">{t.list.outcome.undecided}</option>
        </select>
        <label className="visually-hidden" htmlFor="sort-by">
          {t.list.sortLabel}
        </label>
        <select id="sort-by" className="select" value={sort} onChange={(e) => setParam('sort', e.target.value)}>
          <option value="recent">{t.list.sortRecent}</option>
          <option value="oldest">{t.list.sortOldest}</option>
          <option value="signal">{t.list.sortSignal}</option>
          <option value="name">{t.list.sortName}</option>
        </select>
      </div>

      <p className="faint" aria-live="polite">
        {t.list.count(rows.length)}
      </p>

      {rows.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <h2 style={{ fontSize: '1.1rem' }}>{t.list.emptyTitle}</h2>
          <p className="muted" style={{ margin: 0 }}>
            {t.list.emptyBody}
          </p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="startup-table">
            <thead>
              <tr>
                <th scope="col">{t.list.colStartup}</th>
                <th scope="col">{t.list.colSignal}</th>
                <th scope="col">{t.list.colStage}</th>
                <th scope="col">{t.list.colSubmitted}</th>
                <th scope="col">{t.list.colRevenue}</th>
                <th scope="col">{t.list.colOutcome}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link to={`/app/startups/${s.id}`} className="row-link">
                      {s.name}
                    </Link>
                    <span className="faint" style={{ display: 'block', maxWidth: 340 }}>
                      {s.oneLiner}
                    </span>
                  </td>
                  <td>
                    <SignalTag signal={s.signal} overridden={s.signalOverridden} />
                  </td>
                  <td>
                    <StageBadge stage={s.stage} />
                  </td>
                  <td className="num">{formatDate(s.submittedAt, locale)}</td>
                  <td className="num">{s.metrics.revenue}</td>
                  <td>{s.decision ? t.decision[s.decision] : <span className="faint">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
