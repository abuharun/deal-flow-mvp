import { Link } from 'react-router-dom'
import { useStore } from '../../lib/store'
import { STEP_KEYS } from '../../lib/types'
import { STEP_META } from './steps'
import { formatDate, DECISION_LABEL } from '../../lib/format'
import { ClockIcon } from '../../components/icons'
import { StubTag } from '../../components/ui'

export default function FounderHome() {
  const { state, founderStartup } = useStore()
  const draft = state.draft
  const started = draft.updatedAt !== null
  const nextStep = STEP_KEYS.find((k) => !draft.completed.includes(k)) ?? 'ask'
  const verdictSent = founderStartup?.verdict?.sentAt

  // Decision ready
  if (founderStartup && verdictSent) {
    return (
      <section aria-labelledby="status-heading">
        <p className="status-chip" style={{ color: 'var(--green-ink)' }}>
          Qaror tayyor
        </p>
        <h1 id="status-heading" style={{ marginTop: 14 }}>
          Xulosangiz keldi, {state.session?.name.split(' ')[0]}.
        </h1>
        <p className="muted" style={{ maxWidth: 520 }}>
          Hamkor <strong>{founderStartup.name}</strong> bo'yicha tahlilni yakunlab, sizga halol va
          asoslangan xulosa yozdi: <strong>{DECISION_LABEL[founderStartup.verdict!.decision]}</strong>.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '20px 0 28px' }}>
          <Link to="/apply/verdict" className="btn btn-primary btn-lg">
            Xulosani ko'rish
          </Link>
          <Link to="/apply/verdict/letter.pdf" className="btn btn-secondary">
            Xulosa xati (PDF)
          </Link>
        </div>
        <SubmittedSummary />
      </section>
    )
  }

  // Under review
  if (founderStartup) {
    return (
      <section aria-labelledby="status-heading">
        <div className="pending-hero card">
          <div className="glyph">
            <ClockIcon />
          </div>
          <h1 id="status-heading" style={{ fontSize: '1.6rem' }}>
            {founderStartup.name} ko'rib chiqilmoqda
          </h1>
          <p className="muted" style={{ maxWidth: 460, margin: '0 auto' }}>
            Har bir topshirilgan startapni haqiqiy hamkor o'qiydi — bu yerda bir zumlik hukmlar yo'q. Halol muddat:
            aksariyat tahlillar <strong>besh ish kuni</strong> ichida yakunlanadi. Qaror tayyor
            bo'lishi bilan sizga xabar beramiz.
          </p>
          <p className="faint" style={{ marginTop: 10 }}>
            Topshirildi: {formatDate(founderStartup.submittedAt)} · baholash to'lovi to'langan
          </p>
        </div>
        <ol className="timeline" style={{ marginTop: 26 }}>
          <li className="done">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Topshirildi</strong>
              <p className="faint" style={{ margin: 0 }}>
                Olti bo'limingiz va ilovalaringiz qabul qilindi.
              </p>
            </div>
          </li>
          <li className="done">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Standartlashtirildi</strong>
              <p className="faint" style={{ margin: 0 }}>
                Hikoyangiz investorlar o'qiydigan formatga keltirildi. Asl so'zlaringizni ham inson
                ko'radi — har doim.
              </p>
            </div>
          </li>
          <li className="current">
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Hamkor tahlili</strong>
              <p className="faint" style={{ margin: 0 }}>
                Venchur hamkori topshirgan startapingizni o'rganib, da'volaringizni tekshirmoqda.
              </p>
            </div>
          </li>
          <li>
            <span className="dot" aria-hidden="true" />
            <div>
              <strong>Sizning xulosangiz</strong>
              <p className="faint" style={{ margin: 0 }}>
                Sababi bilan yozilgan halol qaror, o'z tilingizda.
              </p>
            </div>
          </li>
        </ol>
        <div className="demo-note" style={{ marginTop: 24 }}>
          <StubTag>Demo</StubTag> Ikkinchi tomonni o'ynash uchun: chiqing, venchur hamkori sifatida
          kiring, pipeline'da <strong>{founderStartup.name}</strong> kartasini oching, qaror qiling va
          xulosani yuboring. Keyin bu yerga qayting.
        </div>
        <div style={{ marginTop: 20 }}>
          <SubmittedSummary />
        </div>
      </section>
    )
  }

  // Draft in progress
  if (started) {
    const doneCount = draft.completed.length
    return (
      <section aria-labelledby="status-heading">
        <p className="status-chip">Topshirish davom etmoqda</p>
        <h1 id="status-heading" style={{ marginTop: 14 }}>
          Yana xush kelibsiz{draft.startupName ? ` — ${draft.startupName}` : ''}.
        </h1>
        <p className="muted" style={{ maxWidth: 520 }}>
          Jarayoningiz shu qurilmada saqlangan. <span className="num">6</span> bo'limdan{' '}
          <span className="num">{doneCount}</span> tasini to'ldirdingiz — qoldirgan joyingizdan davom
          eting.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 20 }}>
          <Link to={`/apply/submit?step=${nextStep}`} className="btn btn-primary btn-lg">
            Davom etish — {STEP_META[nextStep].title}
          </Link>
        </div>
      </section>
    )
  }

  // Empty
  return (
    <section aria-labelledby="status-heading">
      <h1 id="status-heading">Startapingiz investitsiyaga loyiqmi — bilib olaylik.</h1>
      <p className="muted" style={{ maxWidth: 540 }}>
        Biznesingiz haqida oltita halol savolga javob berasiz — muammo, mahsulot, bozor, natijalar,
        jamoa va so'rovingiz. Bu 20–30 daqiqa oladi, yozganingiz avtomatik saqlanadi va telefonda
        bemalol ishlaydi. Har bir topshirilgan startapni haqiqiy venchur hamkori o'qib, sizga haqqoniy xulosa yozadi.
      </p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 22 }}>
        <Link to="/apply/submit?step=problem" className="btn btn-primary btn-lg">
          Startapingizni topshiring
        </Link>
      </div>
      <hr className="divider" />
      <h2 style={{ fontSize: '1.1rem' }}>Topshirganingizdan keyin nima bo'ladi</h2>
      <ol className="timeline">
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>Baholash to'lovi</strong>
            <p className="faint" style={{ margin: 0 }}>
              Bir martalik to'lov tahlil eshigini ochadi — u har bir topshirishni jiddiy qiladi, bizniki
              bilan birga.
            </p>
          </div>
        </li>
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>Hamkor tahlili</strong>
            <p className="faint" style={{ margin: 0 }}>
              AI standartlashtiradi, inson baholaydi. Aksariyat tahlillar besh ish kuni ichida
              tugaydi.
            </p>
          </div>
        </li>
        <li>
          <span className="dot" aria-hidden="true" />
          <div>
            <strong>Sizning xulosangiz</strong>
            <p className="faint" style={{ margin: 0 }}>
              Sababi bilan aniq qaror — javob «hozircha yo'q» bo'lsa, uni nima o'zgartirishi ham.
            </p>
          </div>
        </li>
      </ol>
    </section>
  )
}

function SubmittedSummary() {
  const { founderStartup } = useStore()
  if (!founderStartup) return null
  return (
    <details className="card card-tight">
      <summary style={{ cursor: 'pointer', fontWeight: 620 }}>
        Topshirilgan startapingiz — {founderStartup.name}
      </summary>
      <div style={{ marginTop: 12 }}>
        <p className="muted" style={{ marginBottom: 14 }}>
          {founderStartup.oneLiner}
        </p>
        {STEP_KEYS.map((k) => (
          <div className="summary-section" key={k}>
            <h4>{STEP_META[k].title}</h4>
            <p>{founderStartup.raw[k] || <span className="faint">To'ldirilmagan.</span>}</p>
          </div>
        ))}
      </div>
    </details>
  )
}
