import type { Attachment, Decision, Lang, Signal, Stage, Startup, StepKey, VerificationItem } from './types'
import { summarizeField, opaqueId } from './simulate'
import { composeVerdict } from './compose'
import { formatDateLong } from './format'

/** The demo VC partner. One partner, one country — per the pilot scope. */
export const VC_NAME = 'Laylo Mirzaeva'
export const VC_EMAIL = 'laylo@bevosita.demo'

/** The demo founder account. */
export const FOUNDER_NAME = 'Dilshod Ergashev'
export const FOUNDER_EMAIL = 'dilshod@bevosita.demo'

export const VALIDATION_FEE = '$199'

export function makeVerification(): VerificationItem[] {
  return [
    { id: 'revenue', label: "Daromad isboti da'voga mos", hint: "Bank ko'chirmasi yoki to'lov provayderi eksporti", done: false },
    { id: 'captable', label: 'Kapital jadvali (cap table) toza', hint: "Asoschilar ulushi butun, egalik tuzilmasi buzilmagan", done: false },
    { id: 'references', label: 'Asoschi haqidagi tavsiyalar tasdiqlandi', hint: "Ikki mustaqil tavsiyachi bilan bog'lanildi", done: false },
    { id: 'registry', label: "Kompaniya ro'yxatdan o'tgani tekshirildi", hint: "Davlat reestri ma'lumoti hujjatlarga mos", done: false },
  ]
}

export interface SeedSpec {
  name: string
  oneLiner: string
  sector: string
  fundingStage: string
  founder: { name: string; email: string; city: string; language: Lang }
  submittedAt: string
  stage: Stage
  signal: Signal
  raw: Record<StepKey, string>
  metrics: { revenue: string; growth: string; ask: string }
  recHeadline: string
  recRationale: string[]
  attachments: Attachment[]
  decision?: Decision
  notes?: string
  verifiedIds?: string[]
  verdictSentAt?: string
}

/** Exported for the Russian display overlay (content.ts), which needs the
 * original Uzbek values to know when a field is still untouched seed data. */
export const SEED_SPECS: SeedSpec[] = [
  {
    name: 'Xarid',
    oneLiner: "Restoran va kafelar uchun B2B ta'minot marketpleysi",
    sector: 'B2B marketpleys',
    fundingStage: 'Seed',
    founder: { name: 'Aziza Karimova', email: 'aziza@xarid.uz', city: 'Toshkent', language: 'uz' },
    submittedAt: '2026-07-26T09:40:00Z',
    stage: 'new',
    signal: 'high',
    raw: {
      problem:
        "Toshkentdagi restoranlar sabzavot, go'sht va quruq mahsulotlarni Chorsu bozoridan tanish-bilishchilik va naqd pul orqali sotib oladi. Narxlar haftadan haftaga 20% gacha o'zgaradi, hech qanday chek yo'q, oshpaz esa har kuni ertalab ikki soatini yetkazib beruvchilarga qo'ng'iroq qilishga sarflaydi. Egalari aslida qancha xarajat qilayotganini ko'ra olmaydi.",
      product:
        "Xarid — restoranlarni tekshirilgan ulgurji yetkazib beruvchilar bilan bog'laydigan buyurtma ilovasi. Restoran 22:00 gacha bitta buyurtma beradi; biz uni yetkazib beruvchilar bo'yicha jamlab, 07:00 gacha yagona batafsil hisob-faktura bilan yetkazib beramiz. Savatdan 6% marja olamiz.",
      market:
        "Toshkentning o'zida 12 000 ga yaqin, mamlakat bo'ylab 40 000 dan ortiq ro'yxatdan o'tgan umumiy ovqatlanish korxonasi bor. O'rta restoranning oziq-ovqat xaridi oyiga $8 000–15 000 ni tashkil qiladi. Toshkentdagi yillik xarid oqimini $600M deb baholaymiz.",
      traction:
        "9 oydan beri ishlaymiz. 214 ta restoran kamida haftada bir marta, 61 tasi har kuni buyurtma beradi. O'tgan oy GMV $412 000, bizning yalpi daromadimiz $24 700 bo'ldi. So'nggi olti oyda GMV o'sishi o'rtacha oyiga 18%. Oylik churn 3% dan past.",
      team:
        "Aziza Karimova (CEO) besh yil davomida Bon! kafelar tarmog'ining ta'minotini boshqargan. Rustam Aliyev (CTO) Uzumda logistika marshrutlash tizimini qurgan. Jami olti xodim, uchtasi yetkazib berish jamoasida. Ikkala asoschi ham to'liq stavkada ishlaydi va birgalikda 82% ulushga ega.",
      ask:
        "Samarqand va Buxoroga kengayish, ikki savdo rahbarini yollash hamda yetkazib beruvchilar uchun ombor vositalarini qurish maqsadida 12% evaziga $500 000 seed jalb qilmoqdamiz. Ikki mahalliy angel-investordan $180 000 kelishilgan.",
    },
    metrics: { revenue: '$24.7k yalpi / oy', growth: '+18% GMV oyiga', ask: '$500k seed' },
    recHeadline: "Tez orada sinchiklab ko'rishga arziydi",
    recRationale: [
      "Ko'rsatilgan daromad va oyiga 18% GMV o'sishi bu pipeline uchun kuchli natija; to'lov eksportlari bilan solishtiring.",
      "Ikkala asoschida ham bevosita soha tajribasi bor; tavsiyalarni tekshirish qiyin bo'lmasa kerak.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'xarid-seed-deck.pdf' },
      { label: 'Daromad isboti', kind: 'revenue', fileName: 'payme-export-jun.xlsx' },
      { label: 'Data room', kind: 'dataroom', fileName: 'drive.google.com/xarid-dataroom' },
    ],
  },
  {
    name: 'TezYol',
    oneLiner: "Markaziy Osiyo bo'ylab uzoq masofali yuk tashish uchun raqamli yuk birjasi",
    sector: 'Logistika',
    fundingStage: 'Seed',
    founder: { name: 'Bekzod Rahimov', email: 'bekzod@tezyol.uz', city: 'Toshkent', language: 'ru' },
    submittedAt: '2026-07-25T14:10:00Z',
    stage: 'new',
    signal: 'high',
    raw: {
      problem:
        "Toshkentdan Almatiga qatnovchi yuk mashinasi 40% hollarda bo'sh qaytadi, chunki yuk topish Telegram guruhlari va telefon qo'ng'iroqlari orqali, 15–20% komissiya oladigan dispetcherlar qo'lida. Yuk jo'natuvchilar yukni kuzata olmaydi, haydovchilar esa haqini olish uchun kunlab kutadi.",
      product:
        "TezYol tekshirilgan yuk jo'natuvchilarni tekshirilgan tashuvchilar bilan biriktiradi, hujjatlarni raqamli yuritadi va yetkazilganlik isbotidan keyin 48 soat ichida haydovchiga pul to'laydi — biz 8% olamiz. GPS kuzatuv arzon telefon ushlagichi va haydovchi ilovamiz orqali ishlaydi.",
      market:
        "O'zbekiston savdo yuklarining 60% ini avtomobil yo'llari orqali tashiydi. Ichki va xalqaro yuk tashish bozori yiliga $2.1B ga baholanadi. Bozor juda tarqoq: eng yirik avtopark egasida 200 tadan kam mashina bor.",
      traction:
        "11 oy oldin ishga tushdik. 1 840 ro'yxatdan o'tgan haydovchi, 96 faol yuk jo'natuvchi. 3 100 ta yetkazma bajarildi; o'tgan oy 640 ta yetkazma va $92 000 komissiya daromadi. Oyiga 14% o'sish. May oyida ochilgan Qozog'iston yo'nalishi allaqachon hajmning 20% ini beradi.",
      team:
        "Bekzod Rahimov (CEO) 120 mashinali avtoparkda operatsiyalar direktori bo'lgan. Elyor G'aniyev (CTO) — sobiq EPAM xodimi. To'qqiz kishi. Asoschilar ulushi 74%.",
      ask:
        "Haydovchilarga tez to'lov fondini moliyalashtirish, Qozog'iston yo'nalishini kengaytirish va xalqaro hujjatlar bo'yicha komplayens rahbarini yollash uchun 15% evaziga $750 000 jalb qilmoqdamiz.",
    },
    metrics: { revenue: '$92k komissiya / oy', growth: '+14% oyiga', ask: '$750k seed' },
    recHeadline: "Tez orada sinchiklab ko'rishga arziydi",
    recRationale: [
      "Hajm va daromad raqamlari salmoqli; tez to'lov fondi — tekshirilishi kerak bo'lgan asosiy moliyaviy xavf.",
      "Xalqaro kengayish da'volarini Qozog'iston bo'yicha haqiqiy yetkazma yozuvlari bilan solishtirish kerak.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'tezyol-deck-v4.pdf' },
      { label: 'Daromad isboti', kind: 'revenue', fileName: 'shipments-ledger-2026.xlsx' },
    ],
  },
  {
    name: 'BilimPay',
    oneLiner: "Kasbiy kurslar va bootcamplar uchun bo'lib to'lash",
    sector: 'Fintech · EdTech',
    fundingStage: 'Pre-seed',
    founder: { name: 'Nodira Yusupova', email: 'nodira@bilimpay.uz', city: 'Toshkent', language: 'uz' },
    submittedAt: '2026-07-24T08:05:00Z',
    stage: 'new',
    signal: 'medium',
    raw: {
      problem:
        "Toshkentdagi IT bootcamplar oldindan $800–1 500 turadi — bu o'rtacha oylikning uch-besh oyligi. Banklar kurs to'lovini moliyalashtirmaydi, shu bois o'quv markazlari malakali nomzodlarning yarmini aynan to'lov bosqichida yo'qotadi.",
      product:
        "BilimPay talabaga kontrakt pulini 6–12 oyga bo'lib to'lash imkonini beradi. Biz o'quv markaziga 9% chegirma bilan oldindan to'laymiz va pulni talabadan yig'amiz. Skoring bandlik holati, kafil va biz yig'adigan kursni tugatish ko'rsatkichlariga tayanadi.",
      market:
        "O'zbekistonda yiliga taxminan 90 000 kishi kasbiy kurslar uchun pul to'laydi — bu qariyb $70M lik kontrakt bozori va IT-park soliq imtiyozlari tufayli tez o'smoqda.",
      traction:
        "5 oydan beri 4 ta o'quv markazi bilan pilot yuritamiz. 312 ta kredit berildi, jami $214 000. Hozircha defolt darajasi 4.1%, ammo eng eski kohorta atigi besh oylik. Ikki markaz barcha guruhlariga kengaytirishni so'radi.",
      team:
        "Nodira Yusupova (CEO) olti yil Kapitalbankda kredit-risk tahlilchisi bo'lgan. CTO qidirilmoqda — mahsulot hozircha pudrat asosidagi dasturchilar jamoasida ishlab chiqilgan. Asoschi ulushi 95%.",
      ask:
        "Asosan kredit portfeli va ilk shtatdagi muhandislarni yollash uchun 10% evaziga $300 000 pre-seed jalb qilmoqdamiz.",
    },
    metrics: { revenue: '$214k kredit berilgan', growth: "4 o'quv markazi piloti", ask: '$300k pre-seed' },
    recHeadline: 'Istiqbolli, ammo ochiq savollar bor',
    recRationale: [
      "Kredit hajmi haqiqiy, ammo defolt ma'lumotlari ishonch uchun hali juda yosh — 4.1% raqamini dastlabki deb qabul qiling.",
      "Texnik hammuassis yo'q; autsors qilingan mahsulot — bevosita ko'tarishga arziydigan xavf.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'bilimpay-preseed.pdf' },
      { label: 'Kredit portfeli eksporti', kind: 'revenue', fileName: 'loan-tape-jul.csv' },
    ],
  },
  {
    name: 'Navbat',
    oneLiner: 'Xususiy klinikalar uchun qabul va navbat boshqaruvi',
    sector: 'HealthTech SaaS',
    fundingStage: 'Pre-seed',
    founder: { name: 'Malika Azimova', email: 'malika@navbat.uz', city: 'Samarqand', language: 'ru' },
    submittedAt: '2026-07-22T11:30:00Z',
    stage: 'new',
    signal: 'medium',
    raw: {
      problem:
        "O'zbekistondagi xususiy klinikalar bemorlarni telefon orqali qog'oz jurnallarga yozadi. Ikki marta yozilishlar va kelmay qolishlar shifokor vaqtining qariyb beshdan birini bekor sarflaydi, bemorlar esa yo'laklarda soatlab, hech qanday ma'lumotsiz navbat kutib o'tiradi.",
      product:
        "Klinika uchun qabul jadvali paneli hamda bemorlar uchun yozilish, eslatma va jonli navbat o'rnini ko'rsatadigan Telegram-bot. Klinikalar har bir filial uchun oyiga $49 to'laydi. O'rnatish yarim kun oladi va qabulxonadagi mavjud kompyuterda ishlaydi.",
      market:
        "O'zbekistonda 6 500 ga yaqin litsenziyalangan xususiy klinika bor; to'rtta yirik shaharda ulardan 2 000 tasiga yeta olamiz. Oyiga $49 dan bu $3.8M lik xizmat ko'rsatiladigan bozor — o'zi kichik, lekin klinika to'lovlari va yozuvlariga kirish eshigi.",
      traction:
        "7 oyda 38 ta to'lovchi klinika, $1 860 MRR, oyiga qariyb 9% o'sish. Bizning klinikalarimizda kelmay qolish 22% dan 9% ga tushdi. 3 klinika ketdi — barchasi bitta shifokorli amaliyotlar.",
      team:
        "Malika Azimova (CEO) 3 filialli stomatologiya tarmog'ining operatsiyalarini boshqargan. Aibek Salimov (CTO) mahsulotni yolg'iz qurgan, sobiq frilanser. Ikkalasi ham to'liq stavkada, ulush 100% asoschilarda.",
      ask:
        "Toshkent uchun ikki sotuv mutaxassisini yollash va klinikalar so'rayotgan to'lov modulini qurish uchun 8% evaziga $150 000 jalb qilmoqdamiz.",
    },
    metrics: { revenue: '$1.9k MRR', growth: '+9% oyiga', ask: '$150k pre-seed' },
    recHeadline: 'Istiqbolli, ammo ochiq savollar bor',
    recRationale: [
      "Mijozlarning qolishi va o'lchangan kelmay qolish kamayishi bu miqyos uchun haqiqiy signal.",
      "Ko'rsatilgan SaaS bozori kichik; venchur imkoniyat — to'lovlar yo'nalishi. Uning qanchalik realligini so'rang.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [{ label: 'Pitch-dek', kind: 'deck', fileName: 'navbat-deck.pdf' }],
  },
  {
    name: 'AgroSensor',
    oneLiner: "Paxta fermalari uchun tuproq namligi sensorlari va sug'orish maslahati",
    sector: 'AgriTech',
    fundingStage: 'Pre-seed',
    founder: { name: 'Jasur Toshpulatov', email: 'jasur@agrosensor.uz', city: "Farg'ona", language: 'uz' },
    submittedAt: '2026-07-20T16:45:00Z',
    stage: 'new',
    signal: 'low',
    raw: {
      problem:
        "Paxta fermalari 30–40% ortiqcha sug'oradi, chunki suv tuproq ma'lumotiga emas, qat'iy jadvalga qarab beriladi. Suv kvotalari yildan yilga qattiqlashmoqda, Orol havzasi cheklovlari esa o'n yil ichida bostirib sug'orishni iqtisodiy jihatdan imkonsiz qiladi.",
      product:
        "Mahalliy sharoitda $60 lik ehtiyot qismlardan yig'iladigan LoRa tuproq namligi zondi hamda ferma boshqaruvchisiga qachon va qancha sug'orishni aytadigan SMS-maslahat xizmati. 25 ta prototip qurdik va hamkor fermada bitta dala sinovi o'tkazdik.",
      market:
        "O'zbekistonda qariyb 80 000 fermer xo'jaligiga bo'lingan 1 mln gektar paxta maydoni bor, asosan davlat kvotali klasterlar. Sotish uchun klaster darajasidagi yoki davlat shartnomalari kerak.",
      traction:
        "40 gektarda yakunlangan bitta dala sinovi hosilni yo'qotmasdan suvni 24% tejashni ko'rsatdi — kuchli natija, ammo bitta fermadagi bitta mavsum xolos. Hali daromad yo'q. Ikki klaster niyat xatini imzoladi, shartnoma emas.",
      team:
        "Jasur Toshpulatov (CEO) — irrigatsiya muhandisi, TIQXMMI (TIIAME) doktoranturasini tugatgan. Ikki yarim stavkali talaba bilan yolg'iz ishlaydi. Hozircha institutda yarim stavkada band.",
      ask:
        "500 ta qurilma ishlab chiqarish va 2027 mavsumi uchun uchta pullik klaster pilotini o'tkazish maqsadida 15% evaziga $200 000 jalb qilmoqdamiz.",
    },
    metrics: { revenue: 'Hali daromadsiz', growth: '1 dala sinovi', ask: '$200k pre-seed' },
    recHeadline: "Bu pipeline uchun hali erta ko'rinadi",
    recRationale: [
      "Hali tijoriy natija ko'rsatilmagan; asos — bitta dala sinovi va niyat xatlari, xolos.",
      "Davlat bilan bog'liq klasterlarga yolg'iz, yarim stavkali asoschining sotishi og'ir kombinatsiya — to'liq stavkaga o'tish rejasini so'rang.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'agrosensor-deck.pdf' },
      { label: 'Dala sinovi hisoboti', kind: 'other', fileName: 'trial-report-2026.pdf' },
    ],
  },
  {
    name: 'OshMarket',
    oneLiner: "Mahalliy dark-store'lardan 30 daqiqada oziq-ovqat yetkazib berish",
    sector: "Iste'mol · Q-commerce",
    fundingStage: 'Seed',
    founder: { name: 'Sardor Umarov', email: 'sardor@oshmarket.uz', city: 'Toshkent', language: 'uz' },
    submittedAt: '2026-07-17T10:20:00Z',
    stage: 'in-review',
    signal: 'medium',
    raw: {
      problem:
        "Toshkentning yangi turar-joy massivlaridagi ishlaydigan oilalar bozor va yirik supermarketlardan uzoqda yashaydi. Mavjud yetkazib berish ilovalari 2–4 soat oladi va mahsulotni so'ramasdan boshqasiga almashtiradi.",
      product:
        "Har biri 1 200 SKU li uchta dark-store, elektr mopedlardagi o'z kuryerlarimiz, 3 km radiusda 30 daqiqalik va'da. O'rtacha savat $14, yetkazish haqi $0.90, hozirgi aralash marja buyurtma boshiga −$0.40.",
      market:
        "Toshkent aglomeratsiyasida 3 mln aholi yashaydi; biz mo'ljallagan massivlarda daromadi o'rtachadan yuqori 600 000 aholi bor. Shahar bo'yicha oziq-ovqat bozori $1.5B.",
      traction:
        "5 400 oylik faol mijoz, o'tgan oy 31 000 buyurtma, $430 000 GMV. Buyurtmalar oyiga 11% o'sadi. Yunit-ekonomika salbiy, lekin yaxshilanmoqda: to'rt oy oldin marja −$1.10 edi.",
      team:
        "Sardor Umarov (CEO) avval ikki Qozog'iston shahrida Wolt operatsiyalarini yo'lga qo'ygan. To'rt shahar menejeridan iborat kuchli operatsion jamoa. CTO ichkaridan ko'tarilgan texnik rahbar.",
      ask:
        "8 ta do'konda marja bo'yicha o'zini qoplashga chiqish va Series A dan oldin modelni isbotlash uchun 18% evaziga $1.2M seed jalb qilmoqdamiz.",
    },
    metrics: { revenue: '$430k GMV / oy', growth: '+11% oyiga, marja −$0.40', ask: '$1.2M seed' },
    recHeadline: 'Istiqbolli, ammo ochiq savollar bor',
    recRationale: [
      "Miqyos va o'sish haqiqiy, ammo har bir buyurtma hali ham zarar keltiradi — butun savol marja trayektoriyasida.",
      "Bu kategoriya dunyo bo'ylab katta kapital yoqib yuborgan; bu yerda tarkibiy jihatdan nima boshqacha ekanini so'rang.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'oshmarket-seed.pdf' },
      { label: 'Yunit-ekonomika modeli', kind: 'other', fileName: 'ue-model-jul.xlsx' },
      { label: 'Data room', kind: 'dataroom', fileName: 'notion.so/oshmarket-dr' },
    ],
    verifiedIds: ['registry'],
  },
  {
    name: 'KassaBox',
    oneLiner: "Kichik do'konlar uchun kassa tizimi va avtomatik soliq hisoboti",
    sector: 'Fintech SaaS',
    fundingStage: 'Seed',
    founder: { name: 'Timur Ibragimov', email: 'timur@kassabox.uz', city: 'Toshkent', language: 'ru' },
    submittedAt: '2026-07-15T09:00:00Z',
    stage: 'in-review',
    signal: 'high',
    raw: {
      problem:
        "O'zbekistondagi har bir savdo nuqtasi qonun bo'yicha onlayn fiskal kassa yuritishi shart, ammo sertifikatlangan qurilmalar noqulay, soliq hisoboti esa do'konlardan har oy bir kunlik buxgalter mehnatini talab qiladi. Xatolar uchun jarimalar juda og'ir.",
      product:
        "Istalgan $80 lik telefonni sertifikatlangan fiskal kassaga aylantiradigan Android ilova; soliq hisobotlari avtomatik topshiriladi. Har bir savdo nuqtasi uchun oyiga $12. Soliq qo'mitasi bergan to'rtta fiskal operator litsenziyasidan biri bizda.",
      market:
        "Qariyb 450 000 ro'yxatdan o'tgan savdo nuqtasi talabga bo'ysunishi kerak. Oyiga $12 dan yetib boriladigan bozor taxminan $45M ARR. Litsenziya — himoya devori: yangisini olish navbati ikki yildan uzun.",
      traction:
        "6 800 to'lovchi savdo nuqtasi, $79 000 MRR, so'nggi sakkiz oyda oyiga 12% o'sish. Sof daromad ushlab qolish (NRR) 104%. Distributsiya — bizni mijozlariga qayta sotadigan 40 ta buxgalteriya firmasi orqali.",
      team:
        "Timur Ibragimov (CEO) avval buxgalteriya dasturlari kompaniyasini qurib sotgan. CTO va CFO u bilan o'sha yerda ishlagan. O'n to'rt xodim. Angel-raunddan keyin asoschilar ulushi 68%.",
      ask:
        "Ish haqi bo'yicha komplayens qo'shish va buxgalter-hamkorlar kanalini butun mamlakatga kengaytirish uchun 12% evaziga $900 000 seed jalb qilmoqdamiz.",
    },
    metrics: { revenue: '$79k MRR', growth: '+12% oyiga, NRR 104%', ask: '$900k seed' },
    recHeadline: "Tez orada sinchiklab ko'rishga arziydi",
    recRationale: [
      "Regulyator himoyasi bilan kuchli takroriy daromad; litsenziya da'vosi markaziy va tekshirsa bo'ladigan fakt — tekshiring.",
      "Xuddi shu sohada muvaffaqiyatli chiqishi bo'lgan takroriy asoschi; tavsiyalar tez tasdiqlansa kerak.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'kassabox-seed-v2.pdf' },
      { label: 'Daromad isboti', kind: 'revenue', fileName: 'mrr-export-jul.csv' },
      { label: 'Fiskal operator litsenziyasi', kind: 'other', fileName: 'license-scan.pdf' },
    ],
    verifiedIds: ['registry', 'revenue'],
    notes: "litsenziya himoyasi haqiqiyga o'xshaydi, reestrni tekshirdim\ndaromad eksporti aytilgan mrr bilan 2% farq ichida mos\nbuxgalteriya kanalidan yana 2 ta hamkor tavsiyasi kerak",
  },
  {
    name: 'SolarUz',
    oneLiner: 'Kichik zavod va fermalar uchun moliyalashtirilgan tom usti quyosh panellari',
    sector: 'ClimateTech',
    fundingStage: 'Seed',
    founder: { name: 'Dilnoza Saidova', email: 'dilnoza@solaruz.uz', city: 'Toshkent', language: 'uz' },
    submittedAt: '2026-07-02T13:15:00Z',
    stage: 'recommended',
    signal: 'high',
    raw: {
      problem:
        "Kichik zavodlar o'sib borayotgan tijoriy elektr tariflarini to'laydi va ishlab chiqarishni to'xtatadigan uzilishlardan aziyat chekadi. Bu yerda tom usti quyosh paneli to'rt yilda o'zini qoplaydi, ammo hech bir bank kichik biznes uchun buni moliyalashtirmaydi.",
      product:
        "Biz quyosh panellarini oldindan to'lovsiz o'rnatamiz va elektr energiyasini xo'jayinga tarmoq tarifidan 15% arzon narxdagi 7 yillik elektr xarid shartnomasi (PPA) asosida sotamiz. O'zini qoplagach, keyingi tejamkorlikni bo'lishamiz.",
      market:
        "O'zbekiston 2030 yilgacha 25% qayta tiklanuvchi energiya maqsadini qo'ygan va taqsimlangan quyosh energetikasiga bevosita subsidiyalar beradi. 18 000 ga yaqin mos tijoriy tom bor deb baholaymiz; o'rtacha o'rnatish $40 000.",
      traction:
        "23 ta obyekt ishlamoqda, $1.1M sarflangan, oylik takroriy elektr daromadi $31 000, 14 oyda birorta to'lov defolti yo'q. 61 ta imzolangan niyat xatidan iborat navbat. Panel ta'minoti ikki Xitoy ishlab chiqaruvchisi bilan shartnoma qilingan.",
      team:
        "Dilnoza Saidova (CEO) yetti yil OTBda (ADB) energetika loyihalarini moliyalashtirgan. CTO o'n yil sanoat elektromontajini boshqargan. O'n bir xodim, uchta litsenziyalangan o'rnatish brigadasi.",
      ask:
        "Keyingi 45 ta o'rnatishni moliyalashtirish uchun $2M jalb qilmoqdamiz ($800k ulush 10% evaziga, $1.2M qarz liniyasi).",
    },
    metrics: { revenue: '$31k takroriy / oy', growth: '23 obyekt, 0 defolt', ask: '$2M (ulush+qarz)' },
    recHeadline: "Tez orada sinchiklab ko'rishga arziydi",
    recRationale: [
      "14 oy davomida birorta defoltisiz takroriy daromad — bu pipeline uchun favqulodda kuchli signal.",
      "Model kapital talab qiladi; ulush/qarz nisbati va PPA shartnomalarining ijro etilishi jiddiy tekshiruvga loyiq.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'solaruz-seed.pdf' },
      { label: 'Daromad isboti', kind: 'revenue', fileName: 'ppa-receipts-h1.xlsx' },
      { label: 'Data room', kind: 'dataroom', fileName: 'drive.google.com/solaruz-dr' },
    ],
    verifiedIds: ['registry', 'revenue', 'references', 'captable'],
    decision: 'recommend',
    notes:
      "pipeline'dagi eng yaxshi aktiv bilan ta'minlangan bitim, daromad ppa kvitansiyalari bilan tasdiqlandi\nceo bu chorakda ko'rgan eng kuchli asoschim, adb maktabi sezilib turibdi\nppa shartnomasining ijrosi ochiq huquqiy savol, lekin mahalliy yurist muammo yo'q deydi\nagar qarz liniyasi amalga oshmasa, ulush mablag'ining o'zi rejani qoplamaydi",
    verdictSentAt: '2026-07-10T15:00:00Z',
  },
  {
    name: 'DoriGo',
    oneLiner: 'Insulin va biopreparatlar uchun sovuq zanjirli litsenziyalangan dorixona yetkazmasi',
    sector: 'HealthTech',
    fundingStage: 'Seed',
    founder: { name: 'Kamola Rashidova', email: 'kamola@dorigo.uz', city: 'Toshkent', language: 'en' },
    submittedAt: '2026-06-20T10:00:00Z',
    stage: 'advanced',
    signal: 'high',
    raw: {
      problem:
        "O'zbekistonda diabet va surunkali kasalligi bor bemorlar dori izlab shahar kezadi, insulin kabi sovuq zanjir talab qiladigan dorilar esa noto'g'ri saqlash tufayli tez-tez yaroqsiz holga keladi. Retseptli dorilarni qonuniy yetkazib berish imkoni yo'q.",
      product:
        "DoriGo — mamlakatdagi birinchi litsenziyalangan dorixona-yetkazma operatori: dorixona litsenziyasi bizda, validatsiyadan o'tgan sovuq zanjir kuryerlarimiz ishlaydi va zaxira uchun 120 hamkor dorixona bilan integratsiya qilganmiz. Retseptlarni ilovada shtatdagi farmatsevtlarimiz tekshiradi.",
      market:
        "O'zbekiston chakana farmatsevtika bozori $1.8B va uning 70% i surunkali kasalliklar uchun takroriy xaridlar — yetkazib berish aynan shu takroriy xulq-atvorni egallaydi. Qozog'istonga mintaqaviy kengayish bozorni ikki baravar oshiradi.",
      traction:
        "Oyiga 28 000 buyurtma, $610 000 oylik GMV, 19% komissiya. Buyurtmalarning 62% i takroriy xaridlar. Oyiga 16% o'sish. Sog'liqni saqlash vazirligi raqamli salomatlik strategiyasida bizni misol qilib keltirgan.",
      team:
        "Kamola Rashidova (CEO) — INSEAD MBA darajasiga ega farmatsevt; avval mintaqaviy ulgurji kompaniyada farma distributsiyasini boshqargan. CTO — sobiq Yandex xodimi. Olti litsenziyalangan farmatsevtni o'z ichiga olgan yigirma ikki xodim.",
      ask:
        "Yana beshta shaharga kengayish va Qozog'istonda litsenziyalash jarayonini boshlash uchun 14% evaziga $1.5M seed jalb qilmoqdamiz. Series A yo'li uchun AQSh investorlariga qiziqamiz.",
    },
    metrics: { revenue: '$116k komissiya / oy', growth: '+16% oyiga, 62% takroriy', ask: '$1.5M seed' },
    recHeadline: "Tez orada sinchiklab ko'rishga arziydi",
    recRationale: [
      "Litsenziya himoyasi va takroriy xarid xulq-atvori — joriy pipeline'dagi eng kuchli tarkibiy hikoya.",
      "Asoschi AQSh yo'nalishini ochiq izlayapti; tekshiruvdan o'tsa, AQShga yo'llash uchun mos nomzod.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [
      { label: 'Pitch-dek', kind: 'deck', fileName: 'dorigo-seed.pdf' },
      { label: 'Daromad isboti', kind: 'revenue', fileName: 'orders-gmv-export.xlsx' },
      { label: 'Dorixona litsenziyasi', kind: 'other', fileName: 'dorigo-license.pdf' },
      { label: 'Data room', kind: 'dataroom', fileName: 'drive.google.com/dorigo-dr' },
    ],
    verifiedIds: ['registry', 'revenue', 'references', 'captable'],
    decision: 'advance',
    notes:
      "aynan izlagan bitimimiz, litsenziya + sovuq zanjir haqiqiy himoya, daromad tasdiqlandi\nasoschi allaqachon aqsh darajasida taqdimot qiladi, insead + farma distributsiyasi\nikki farma ulgurji kompaniyasidan tavsiya oldik, ikkalasi ham a'lo\nqozog'iston kengayishi series a hikoyasini mahalliy emas, kontinental qiladi",
    verdictSentAt: '2026-07-01T11:30:00Z',
  },
  {
    name: 'Mahalla',
    oneLiner: "Mahalla xizmatlari va to'lovlari uchun super-ilova",
    sector: "Iste'mol · Ijtimoiy",
    fundingStage: 'Pre-seed',
    founder: { name: 'Otabek Nazarov', email: 'otabek@mahalla.app', city: 'Toshkent', language: 'uz' },
    submittedAt: '2026-06-28T12:00:00Z',
    stage: 'passed',
    signal: 'low',
    raw: {
      problem:
        "Mahalla qo'mitalari kommunal muammolardan to'ylargacha hamma narsani qog'oz e'lonlar va og'zaki gap orqali muvofiqlashtiradi. Yosh aholi o'z mahalla institutlaridan uzilib qolgan.",
      product:
        "Mahallalar uchun super-ilova: e'lonlar, mahalliy xizmatlar bozori, kommunal to'lovlar va jamoa chati. Miqyosga chiqqach, to'lov komissiyalari va mahalliy biznes e'lonlari orqali pul topishni rejalashtirganmiz.",
      market:
        "O'zbekistonda 9 000 dan ortiq mahalla bor va ular amalda butun aholini — 36 mln kishini qamrab oladi. Agar asosiy kanalga aylansak, birgina to'lov aylanmasining o'zi milliardlab dollar.",
      traction:
        "4 oy oldin 12 mahallada ishga tushdik. 3 400 ro'yxatdan o'tgan foydalanuvchi, haftasiga qariyb 400 faol. Hali daromad yo'q; monetizatsiya miqyosda boshlanadi. Davlat bilan hamkorlik muzokarasi davom etmoqda.",
      team:
        "Otabek Nazarov (CEO) — ikkinchi marta asoschi; avvalgi ijtimoiy ilovasi yopilishidan oldin 50 ming yuklab olishga yetgan. Ikki kichik dasturchi. Davlat innovatsiya markazi grantida ishlaymiz.",
      ask:
        "200 mahallaga kengayish va o'sish bo'yicha rahbar yollash uchun 12% evaziga $250 000 jalb qilmoqdamiz.",
    },
    metrics: { revenue: 'Hali daromadsiz', growth: '400 haftalik faol', ask: '$250k pre-seed' },
    recHeadline: "Bu pipeline uchun hali erta ko'rinadi",
    recRationale: [
      "Daromad yo'q, haftalik faollar esa ro'yxatdan o'tganlarga nisbatan kam; ochiq savol — jalb etilganlik.",
      "Bu bosqichdagi super-ilova qamrovi odatda fokussiz mahsulotdan darak beradi; yagona kirish nuqtasi nima ekanini so'rang.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [{ label: 'Pitch-dek', kind: 'deck', fileName: 'mahalla-deck.pdf' }],
    verifiedIds: ['registry'],
    decision: 'pass',
    notes:
      "jalb etilganlik zaif, 4 oydan keyin haftalik faollar 12%, mahsulot suv o'tkazyapti\n3 kishilik jamoa bilan super-ilova qamrovi ishonarli emas, yagona yo'nalish yo'q\nlekin asoschi g'ayratli va o'rganuvchan, jamoa hissi bo'yicha instinktlari yaxshi\nagar bitta xizmatga fokus qilib haftalik faollikni 40% ga chiqarsa, yana ko'raman\nagar birgina kommunal to'lovlarning o'zi real takroriy foydalanish ko'rsatsa, qayta ko'rib chiqaman",
    verdictSentAt: '2026-07-08T09:45:00Z',
  },
  {
    name: 'Chevar',
    oneLiner: 'Buyurtma asosidagi tikuvchilik va milliy liboslar marketpleysi',
    sector: "Iste'mol marketpleysi",
    fundingStage: 'Pre-seed',
    founder: { name: 'Gulnora Vahidova', email: 'gulnora@chevar.uz', city: 'Buxoro', language: 'ru' },
    submittedAt: '2026-07-27T07:55:00Z',
    stage: 'new',
    signal: 'low',
    raw: {
      problem:
        "Buyurtma tikuvchilik O'zbekistonda ulkan norasmiy iqtisodiyot — birgina to'y mavsumi minglab atelyelarni oylab band qiladi — ammo yaxshi chevar topish faqat og'zaki tavsiyaga bog'liq, narxlar esa noshaffof.",
      product:
        "Mijozlar chevar portfoliolarini ko'rib, qat'iy narx taklifini oladigan va o'lchov-sinovdan keyin ochiladigan eskrou orqali to'laydigan marketpleys. Biz 10% olamiz. Dastlabki g'oya: mijozga yuboriladigan standart o'lchov to'plamlari.",
      market:
        "Buyurtma kiyim bozorini yiliga $400M deb baholaymiz; u asosan to'ylar va bayramlar atrofida jamlangan. Raqamli o'yinchi hali yo'q.",
      traction:
        "6 hafta oldin ishga tushdik. 46 chevar ulandi, 28 buyurtma yakunlandi, $2 100 GMV. Kohortalar uchun hali juda erta. Ikki oyda organik yig'ilgan 18 000 lik Instagram auditoriyasi bor.",
      team:
        "Gulnora Vahidova (CEO) sakkiz yil 6 kishilik atelyeni boshqargan va Buxoro tikuvchiligida taniqli nom. Texnik hammuassis yo'q; sayt no-code platformada qurilgan.",
      ask:
        "Dasturchi yollash, eskrou oqimini to'g'ri qurish va to'y mavsumidan oldin Toshkentga kengayish uchun 10% evaziga $120 000 jalb qilmoqdamiz.",
    },
    metrics: { revenue: 'Jami $2.1k GMV', growth: '6 hafta ishlamoqda', ask: '$120k pre-seed' },
    recHeadline: "Bu pipeline uchun hali erta ko'rinadi",
    recRationale: [
      "Olti haftalik ma'lumot baholanadigan natija emas; yagona distributsiya signali — organik auditoriya.",
      "Sohada obro'li, ammo texnik salohiyatsiz asoschi — platforma xavfi darhol yuzaga chiqadi.",
      "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.",
    ],
    attachments: [{ label: 'Pitch-dek', kind: 'deck', fileName: 'chevar-intro.pdf' }],
  },
]

function buildStartup(spec: SeedSpec): Startup {
  const summary = {} as Startup['summary']
  for (const key of Object.keys(spec.raw) as StepKey[]) {
    summary[key] = summarizeField(spec.raw[key])
  }
  const verification = makeVerification().map((v) => ({
    ...v,
    done: spec.verifiedIds?.includes(v.id) ?? false,
  }))
  const verdict =
    spec.decision && spec.verdictSentAt
      ? {
          decision: spec.decision,
          en: composeVerdict({
            decision: spec.decision,
            notes: spec.notes ?? '',
            startupName: spec.name,
            founderName: spec.founder.name,
            vcName: VC_NAME,
            lang: 'en',
            dateLabel: formatDateLong(spec.verdictSentAt, 'en'),
          }),
          local: composeVerdict({
            decision: spec.decision,
            notes: spec.notes ?? '',
            startupName: spec.name,
            founderName: spec.founder.name,
            vcName: VC_NAME,
            lang: spec.founder.language,
            dateLabel: formatDateLong(spec.verdictSentAt, spec.founder.language),
          }),
          localLang: spec.founder.language,
          composedAt: spec.verdictSentAt,
          sentAt: spec.verdictSentAt,
          edited: false,
        }
      : null

  return {
    id: opaqueId(spec.name.toLowerCase()),
    name: spec.name,
    oneLiner: spec.oneLiner,
    sector: spec.sector,
    fundingStage: spec.fundingStage,
    founder: spec.founder,
    submittedAt: spec.submittedAt,
    stage: spec.stage,
    signal: spec.signal,
    signalOverridden: false,
    summary,
    raw: spec.raw,
    metrics: spec.metrics,
    recommendation: { signal: spec.signal, headline: spec.recHeadline, rationale: spec.recRationale },
    attachments: spec.attachments,
    verification,
    decision: spec.decision ?? null,
    notes: spec.notes ?? '',
    verdict,
  }
}

export function seedStartups(): Startup[] {
  return SEED_SPECS.map(buildStartup)
}
