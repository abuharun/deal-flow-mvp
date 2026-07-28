import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useStore } from '../../lib/store'
import type { Stage, Startup } from '../../lib/types'
import { SIGNAL_ORDER, STAGE_LABEL, formatDate, cx } from '../../lib/format'
import { SignalTag } from '../../components/ui'

const BOARD_STAGES: Stage[] = ['new', 'in-review', 'recommended', 'advanced']

function sortForColumn(list: Startup[]): Startup[] {
  // Highest signal first so triage starts where it matters; newest breaks ties.
  return [...list].sort((a, b) => {
    const s = SIGNAL_ORDER[a.signal] - SIGNAL_ORDER[b.signal]
    if (s !== 0) return s
    return b.submittedAt.localeCompare(a.submittedAt)
  })
}

export default function Board() {
  const { state, moveStage } = useStore()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const highlighted = params.get('stage')

  const byStage = (stage: Stage) => sortForColumn(state.startups.filter((s) => s.stage === stage))
  const passed = byStage('passed')
  const counts = BOARD_STAGES.map((st) => `${STAGE_LABEL[st]} ${byStage(st).length}`).join(' · ')

  const openCard = (s: Startup) => {
    // Opening a New card moves it to In Review (see IA: VC flow step 2).
    if (s.stage === 'new') moveStage(s.id, 'in-review')
    navigate(`/app/startups/${s.id}`)
  }

  return (
    <div>
      <div className="board-toolbar">
        <h1 style={{ fontSize: '1.5rem', margin: 0 }}>Pipeline</h1>
        <span className="faint num" aria-label={`Bosqichlar bo'yicha soni: ${counts}`}>
          {counts}
        </span>
        <span style={{ marginLeft: 'auto' }}>
          <Link to="/app/startups" className="btn btn-quiet btn-sm">
            Barcha startaplarni qidirish →
          </Link>
        </span>
      </div>

      <div className="board">
        {BOARD_STAGES.map((stage) => {
          const cards = byStage(stage)
          return (
            <section
              key={stage}
              className={cx('board-col', highlighted === stage && 'highlight')}
              aria-labelledby={`col-${stage}`}
            >
              <div className="board-col-head">
                <h2 id={`col-${stage}`}>{STAGE_LABEL[stage]}</h2>
                <span className="faint num">{cards.length}</span>
              </div>
              <div className="board-cards">
                {cards.length === 0 && <p className="board-empty">Hozircha bu yer bo'sh.</p>}
                {cards.map((s) => (
                  <button key={s.id} type="button" className="board-card" onClick={() => openCard(s)}>
                    <span className="name">
                      {s.name}
                      <span className="faint num" style={{ fontWeight: 480 }}>
                        {formatDate(s.submittedAt)}
                      </span>
                    </span>
                    <span className="line">{s.oneLiner}</span>
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <SignalTag signal={s.signal} overridden={s.signalOverridden} />
                      <span className="faint">{s.metrics.revenue}</span>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )
        })}
      </div>

      <details className="passed-strip" open={highlighted === 'passed'}>
        <summary style={{ cursor: 'pointer', fontWeight: 620 }}>
          Rad etilgan · <span className="num">{passed.length}</span>
          <span className="faint" style={{ fontWeight: 420 }}>
            {' '}
            — doska faol ishlar uchun qolishi maqsadida yig'ilgan; to'liq tarix{' '}
            <Link to="/app/startups?stage=passed">Startaplar</Link> bo'limida
          </span>
        </summary>
        <div className="board-cards" style={{ marginTop: 10, maxWidth: 420 }}>
          {passed.map((s) => (
            <button key={s.id} type="button" className="board-card" onClick={() => openCard(s)}>
              <span className="name">{s.name}</span>
              <span className="line">{s.oneLiner}</span>
              <SignalTag signal={s.signal} overridden={s.signalOverridden} />
            </button>
          ))}
          {passed.length === 0 && <p className="board-empty">Hozircha rad etilgan startaplar yo'q.</p>}
        </div>
      </details>
    </div>
  )
}
