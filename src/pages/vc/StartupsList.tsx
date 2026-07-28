import { Link, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import type { Signal, Stage, Startup } from '../../lib/types'
import { DECISION_LABEL, SIGNAL_ORDER, STAGE_LABEL, STAGE_ORDER, formatDate } from '../../lib/format'
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

  let rows = state.startups.filter(
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
      <h1 style={{ fontSize: '1.5rem' }}>Startups</h1>
      <p className="muted" style={{ marginTop: -6 }}>
        The durable archive — every submission ever, searchable. The board is for acting; this is for
        finding.
      </p>

      <div className="list-toolbar" role="search">
        <input
          type="search"
          className="input search"
          placeholder="Search name, summary, sector, founder…"
          aria-label="Search startups"
          value={q}
          onChange={(e) => setParam('q', e.target.value)}
        />
        <label className="visually-hidden" htmlFor="filter-stage">
          Filter by stage
        </label>
        <select id="filter-stage" className="select" value={stage} onChange={(e) => setParam('stage', e.target.value)}>
          <option value="">All stages</option>
          {STAGE_ORDER.map((st) => (
            <option key={st} value={st}>
              {STAGE_LABEL[st]}
            </option>
          ))}
        </select>
        <label className="visually-hidden" htmlFor="filter-signal">
          Filter by signal
        </label>
        <select id="filter-signal" className="select" value={signal} onChange={(e) => setParam('signal', e.target.value)}>
          <option value="">All signals</option>
          <option value="high">High signal</option>
          <option value="medium">Medium signal</option>
          <option value="low">Low signal</option>
        </select>
        <label className="visually-hidden" htmlFor="filter-outcome">
          Filter by outcome
        </label>
        <select id="filter-outcome" className="select" value={outcome} onChange={(e) => setParam('outcome', e.target.value)}>
          <option value="">All outcomes</option>
          <option value="recommend">Recommended</option>
          <option value="advance">Advanced to US</option>
          <option value="pass">Passed</option>
          <option value="undecided">Undecided</option>
        </select>
        <label className="visually-hidden" htmlFor="sort-by">
          Sort
        </label>
        <select id="sort-by" className="select" value={sort} onChange={(e) => setParam('sort', e.target.value)}>
          <option value="recent">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="signal">By signal</option>
          <option value="name">By name</option>
        </select>
      </div>

      <p className="faint" aria-live="polite">
        {rows.length} {rows.length === 1 ? 'startup' : 'startups'}
      </p>

      {rows.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: 40 }}>
          <h2 style={{ fontSize: '1.1rem' }}>Nothing matches</h2>
          <p className="muted" style={{ margin: 0 }}>
            Try fewer filters, or a broader search term.
          </p>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="startup-table">
            <thead>
              <tr>
                <th scope="col">Startup</th>
                <th scope="col">Signal</th>
                <th scope="col">Stage</th>
                <th scope="col">Submitted</th>
                <th scope="col">Revenue</th>
                <th scope="col">Outcome</th>
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
                  <td className="num">{formatDate(s.submittedAt)}</td>
                  <td className="num">{s.metrics.revenue}</td>
                  <td>{s.decision ? DECISION_LABEL[s.decision] : <span className="faint">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
