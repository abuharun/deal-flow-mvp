import { Link } from 'react-router-dom'
import { Wordmark } from '../components/ui'
import { CheckIcon } from '../components/icons'

export default function Landing() {
  return (
    <>
      <header className="landing-header">
        <Wordmark />
        <nav aria-label="Hisob" style={{ display: 'flex', gap: 10 }}>
          <Link to="/login" className="btn btn-quiet">
            Kirish
          </Link>
          <Link to="/signup" className="btn btn-primary">
            Boshlash
          </Link>
        </nav>
      </header>

      <main className="landing-main">
        <section className="hero">
          <h1>
            Startapingiz uchun halol xulosa.
            <br />
            Haqiqiy kapital uchun haqiqiy signal.
          </h1>
          <p className="lede">
            Oqim O'zbekistondagi asoschilarni AQSh venchur kapitali standartlari bilan bog'laydi.
            Startapingizni topshiring, inson ko'rib chiqqan halol xulosa oling — agar u investitsiyaga
            loyiq bo'lsa, oldinga olib boradigan haqiqiy yo'l ham ochiladi.
          </p>
          <div className="hero-actions">
            <Link to="/signup" className="btn btn-primary btn-lg">
              Startapingizni topshiring
            </Link>
            <Link to="/login" className="btn btn-secondary btn-lg">
              Men bitimlarni ko'rib chiqaman
            </Link>
          </div>
        </section>

        <section aria-labelledby="how-heading">
          <h2 id="how-heading">Qanday ishlaydi</h2>
          <div className="landing-grid">
            <article className="card">
              <h3>1 · Siz topshirasiz</h3>
              <p className="muted">
                Olti bosqichli tartibli topshirish jarayoni — muammo, mahsulot, bozor, natijalar, jamoa, so'rov.
                Istalgan payt saqlab, keyin davom eting; internet uzilib turadigan telefon uchun ham
                qulay qilib qurilgan.
              </p>
            </article>
            <article className="card">
              <h3>2 · Biz sizni tushunarli qilamiz</h3>
              <p className="muted">
                AI hikoyangizni investorlar haqiqatda o'qiydigan formatga keltiradi va qay darajada
                turganingizni taxmin qiladi. U e'tiborni tartiblaydi — hech qachon qaror qabul qilmaydi.
              </p>
            </article>
            <article className="card">
              <h3>3 · Hamkor qaror qiladi</h3>
              <p className="muted">
                Haqiqiy venchur hamkori topshirgan startapingizni asl so'zlaringiz bilan solishtirib o'rganadi,
                da'volaringizni tekshiradi va sizga halol xulosa yozadi — o'z tilingizda, sababi bilan.
              </p>
            </article>
          </div>
        </section>

        <section aria-labelledby="principles-heading" style={{ marginTop: 56 }}>
          <h2 id="principles-heading">Bizning va'damiz</h2>
          <div className="landing-grid">
            <article className="card">
              <h3>Avtomatikadan ko'ra ishonch</h3>
              <p className="muted">
                Har bir xulosani inson hamkor ko'rib chiqadi, tahrirlaydi va yuboradi. AI qoralama
                yozadi; u siz bilan hech qachon nazoratsiz gaplashmaydi.
              </p>
            </article>
            <article className="card">
              <h3>Xushomaddan ko'ra halollik</h3>
              <p className="muted">
                Sababi aytilgan «yo'q» muloyim sukutdan qimmatroq. Javob «hozircha yo'q» bo'lsa, uni
                nima o'zgartirishini ham aytamiz.
              </p>
            </article>
            <article className="card">
              <h3>AQSh kapitaliga haqiqiy yo'l</h3>
              <p className="muted">
                Talabdan o'tgan startaplar AQShdagi hamkorlarga shaxsan tanishtiriladi. Ommaviy
                tarqatish yo'q, sovuq ro'yxatlar yo'q.
              </p>
            </article>
          </div>
        </section>

        <section className="card" style={{ marginTop: 56, background: 'var(--brand-wash)' }}>
          <h2 style={{ marginBottom: 6 }}>Haqiqatni bilmoqchi bo'lgan asoschi uchun</h2>
          <p className="muted" style={{ maxWidth: 640 }}>
            Baholash to'lovi sizga boshqa hech kim bermaydigan narsani beradi: jiddiy tahlil va
            to'g'ri javob. Jahon standartlari bo'yicha investitsiyaga loyiqmi, istiqbolli lekin
            ertami, yoki mahalliy biznes sifatida qurilgani ma'qulmi — bilasiz, va nima uchunligini
            ham bilasiz.
          </p>
          <ul style={{ listStyle: 'none', padding: 0, margin: '14px 0 18px', display: 'grid', gap: 8 }}>
            {[
              "Amaldagi venchur hamkorning tartibli tahlili",
              "O'zbek, rus yoki ingliz tilida yozma xulosa",
              "O'zingizda qoladigan rasmiy xulosa xati",
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
            Topshirishni boshlash
          </Link>
        </section>
      </main>

      <footer className="landing-footer">
        <span>Oqim — Toshkent · Ostin. Mahsulot demosi; haqiqiy startaplar qabul qilinmaydi.</span>
        <span>© 2026 Oqim</span>
      </footer>
    </>
  )
}
