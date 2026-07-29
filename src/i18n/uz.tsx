import type { ReactNode } from 'react'
import type { Decision, Signal, Stage, StepKey } from '../lib/types'

/**
 * The Uzbek interface dictionary — the source of truth for the message schema.
 * `Messages` is derived from this object; the Russian dictionary must satisfy
 * the same shape, so a missing or extra key is a type error, not a runtime bug.
 */
export const uz = {
  meta: {
    title: 'Bevosita — halol bitimlar oqimi',
    description:
      "Bevosita — Toshkent va AQSh kapitali o'rtasida halol startap baholovi. Asoschilar haqiqiy xulosa oladi; investorlar haqiqiy signal.",
  },

  common: {
    logout: 'Chiqish',
    cancel: 'Bekor qilish',
    back: 'Orqaga',
    email: 'Email',
    password: 'Parol',
    name: 'Ism',
    profile: 'Profil',
  },

  switcher: {
    label: 'Interfeys tili',
  },

  wordmarkAria: 'Bevosita — bosh sahifa',

  stage: {
    'new': 'Yangi',
    'in-review': "Ko'rib chiqilmoqda",
    'recommended': 'Tavsiya etilgan',
    'advanced': "AQShga yo'llangan",
    'passed': 'Rad etilgan',
  } as Record<Stage, string>,

  /** Badge on a single startup — same as `stage` in Uzbek, singular in Russian. */
  stageBadge: {
    'new': 'Yangi',
    'in-review': "Ko'rib chiqilmoqda",
    'recommended': 'Tavsiya etilgan',
    'advanced': "AQShga yo'llangan",
    'passed': 'Rad etilgan',
  } as Record<Stage, string>,

  signal: {
    high: 'Kuchli signal',
    medium: "O'rtacha signal",
    low: 'Past signal',
  } as Record<Signal, string>,

  decision: {
    recommend: 'Tavsiya qilish',
    advance: "AQShga yo'llash",
    pass: 'Rad etish',
  } as Record<Decision, string>,

  badges: {
    signalOverriddenSr: '(hamkor tomonidan qayta belgilangan)',
    aiDefault: "Simulyatsiya qilingan AI · bu yo'l-yo'riq, xulosa emas",
    aiStandardized: 'Simulyatsiya qilingan AI · standartlashtirilgan',
    stubDefault: 'Simulyatsiya',
  },

  shell: {
    skipToMain: "Asosiy mazmunga o'tish",
    founderSub: 'asoschilar uchun',
    vcSub: 'hamkor',
    accountNavAria: 'Hisob',
    mainNavAria: 'Asosiy',
    pipeline: 'Pipeline',
    startups: 'Startaplar',
    settings: 'Sozlamalar',
    account: 'Hisob',
  },

  notFound: {
    title: 'Sahifa topilmadi',
    body: 'Bu havola hech qayerga olib bormaydi.',
    home: 'Bosh sahifaga qaytish',
  },

  landing: {
    navAria: 'Hisob',
    assessment: 'Baholash',
    login: 'Kirish',
    start: 'Boshlash',
    badge: 'Inson qaror qiladi · AI yordam beradi',
    hero1: 'Startapingiz uchun halol xulosa.',
    hero2: 'Haqiqiy kapital uchun haqiqiy signal.',
    heroAlt:
      "Markaziy Osiyoni jahon kapital markazlari bilan bog'lovchi yorqin tarmoq chiziqlari tasvirlangan ko'k xarita",
    heroCaption: 'Toshkent ↔ Ostin · bitta halol oqim',
    lede: "Bevosita O'zbekistondagi asoschilarni AQSh venchur kapitali standartlari bilan bog'laydi. Startapingizni topshiring, inson ko'rib chiqqan halol xulosa oling — agar u investitsiyaga loyiq bo'lsa, oldinga olib boradigan haqiqiy yo'l ham ochiladi.",
    ctaSubmit: 'Startapingizni topshiring',
    ctaVc: "Men bitimlarni ko'rib chiqaman",
    flowKicker: 'Jarayon',
    howHeading: 'Qanday ishlaydi',
    flowTitle: 'Tartibli topshirishdan halol qarorgacha',
    flowBody:
      "Startap olti bo'limli tartibda topshiriladi; AI uni investorlar o'qiydigan yagona formatga keltiradi; qarorni esa haqiqiy hamkor qabul qiladi. Avtomatik hukm yo'q — texnologiya faqat e'tiborni tartiblaydi.",
    flowAlt:
      "Tarqoq ma'lumot bloklarini tartibli bosqichlarga jamlovchi shaffof modulli quvur tasviri",
    how1Title: 'Siz topshirasiz',
    how1Body:
      "Olti bosqichli tartibli topshirish jarayoni — muammo, mahsulot, bozor, natijalar, jamoa, so'rov. Istalgan payt saqlab, keyin davom eting; internet uzilib turadigan telefon uchun ham qulay qilib qurilgan.",
    how2Title: 'Biz sizni tushunarli qilamiz',
    how2Body:
      "AI hikoyangizni investorlar haqiqatda o'qiydigan formatga keltiradi va qay darajada turganingizni taxmin qiladi. U e'tiborni tartiblaydi — hech qachon qaror qabul qilmaydi.",
    how3Title: 'Hamkor qaror qiladi',
    how3Body:
      "Haqiqiy venchur hamkori topshirgan startapingizni asl so'zlaringiz bilan solishtirib o'rganadi, da'volaringizni tekshiradi va sizga halol xulosa yozadi — o'z tilingizda, sababi bilan.",
    promiseKicker: 'Tamoyillar',
    promiseHeading: "Bizning va'damiz",
    p1Title: "Avtomatikadan ko'ra ishonch",
    p1Body:
      "Har bir xulosani inson hamkor ko'rib chiqadi, tahrirlaydi va yuboradi. AI qoralama yozadi; u siz bilan hech qachon nazoratsiz gaplashmaydi.",
    p2Title: "Xushomaddan ko'ra halollik",
    p2Body:
      "Sababi aytilgan «yo'q» muloyim sukutdan qimmatroq. Javob «hozircha yo'q» bo'lsa, uni nima o'zgartirishini ham aytamiz.",
    p3Title: "AQSh kapitaliga haqiqiy yo'l",
    p3Body:
      "Talabdan o'tgan startaplar AQShdagi hamkorlarga shaxsan tanishtiriladi. Ommaviy tarqatish yo'q, sovuq ro'yxatlar yo'q.",
    feeHeading: "Haqiqatni bilmoqchi bo'lgan asoschi uchun",
    feeBody:
      "Baholash to'lovi sizga boshqa hech kim bermaydigan narsani beradi: jiddiy tahlil va to'g'ri javob. Jahon standartlari bo'yicha investitsiyaga loyiqmi, istiqbolli lekin ertami, yoki mahalliy biznes sifatida qurilgani ma'qulmi — bilasiz, va nima uchunligini ham bilasiz.",
    feeBullets: [
      'Amaldagi venchur hamkorning tartibli tahlili',
      "O'zbek, rus yoki ingliz tilida yozma xulosa",
      "O'zingizda qoladigan rasmiy xulosa xati",
    ],
    feeCta: 'Topshirishni boshlash',
    footerLine: 'Bevosita — Toshkent · Ostin. Mahsulot demosi; haqiqiy startaplar qabul qilinmaydi.',
    footerCopyright: '© 2026 Bevosita',
  },

  auth: {
    loginTitle: 'Kirish',
    loginDemoNote:
      "Bu mahsulot demosi — istalgan parol ishlaydi. Eng tez yo'l: quyidagi demo hisoblardan birini tanlang.",
    demoRolesAria: 'Demo hisoblar',
    founderRole: 'Asoschi',
    founderRoleSub: (email: string) => `${email} · startap topshiradi`,
    vcRole: 'Venchur hamkori',
    vcRoleSub: (email: string) => `${email} · pipeline bilan ishlaydi`,
    emailPlaceholder: 'siz@misol.uz',
    loginButton: 'Kirish',
    forgot: 'Parolni unutdingizmi?',
    newHere: 'Yangimisiz?',
    signupLink: "Ro'yxatdan o'tish",
    signupTitle: 'Hisob yaratish',
    signupIntro: 'Asoschilar shu yerda ro\'yxatdan o\'tadi. Investorlar faqat taklif orqali kiradi.',
    fullName: "To'liq ism",
    passwordHint: 'Kamida 8 ta belgi.',
    signupButton: "Ro'yxatdan o'tish",
    signupDemoNote: (name: string) =>
      `Demo: ro'yxatdan o'tsangiz, demo asoschi ${name} sifatida kirasiz.`,
    haveAccount: 'Hisobingiz bormi?',
    loginLink: 'Kirish',
    resetTitle: 'Parolni tiklash',
    resetSent: 'Tiklash havolasi yuborildi (simulyatsiya) — pochtangizni tekshiring.',
    resetNote: (link: ReactNode) => (
      <>Bu demoda hech qanday email aslida yuborilmaydi. {link}.</>
    ),
    resetBackLink: 'Kirish sahifasiga qaytish',
    resetButton: 'Tiklash havolasini yuborish',
    remembered: 'Esladingizmi?',
  },

  founderHome: {
    statusReady: 'Qaror tayyor',
    readyHeading: (first: string) => `Xulosangiz keldi, ${first}.`,
    readyBody: (name: ReactNode, decision: ReactNode) => (
      <>
        Hamkor <strong>{name}</strong> bo'yicha tahlilni yakunlab, sizga halol va asoslangan xulosa
        yozdi: <strong>{decision}</strong>.
      </>
    ),
    viewVerdict: "Xulosani ko'rish",
    letterPdf: 'Xulosa xati (PDF)',
    pendingHeading: (name: string) => `${name} ko'rib chiqilmoqda`,
    pendingBody: (
      <>
        Har bir topshirilgan startapni haqiqiy hamkor o'qiydi — bu yerda bir zumlik hukmlar yo'q.
        Halol muddat: aksariyat tahlillar <strong>besh ish kuni</strong> ichida yakunlanadi. Qaror
        tayyor bo'lishi bilan sizga xabar beramiz.
      </>
    ),
    submittedOn: (date: string) => `Topshirildi: ${date} · baholash to'lovi to'langan`,
    tlSubmitted: 'Topshirildi',
    tlSubmittedSub: "Olti bo'limingiz va ilovalaringiz qabul qilindi.",
    tlStandardized: 'Standartlashtirildi',
    tlStandardizedSub:
      "Hikoyangiz investorlar o'qiydigan formatga keltirildi. Asl so'zlaringizni ham inson ko'radi — har doim.",
    tlPartner: 'Hamkor tahlili',
    tlPartnerSub: "Venchur hamkori topshirgan startapingizni o'rganib, da'volaringizni tekshirmoqda.",
    tlVerdict: 'Sizning xulosangiz',
    tlVerdictSub: "Sababi bilan yozilgan halol qaror, o'z tilingizda.",
    demoPlay: (name: ReactNode) => (
      <>
        Ikkinchi tomonni o'ynash uchun: chiqing, venchur hamkori sifatida kiring, pipeline'da{' '}
        <strong>{name}</strong> kartasini oching, qaror qiling va xulosani yuboring. Keyin bu yerga
        qayting.
      </>
    ),
    demoTag: 'Demo',
    draftChip: 'Topshirish davom etmoqda',
    welcomeBack: (name: string | null) => `Yana xush kelibsiz${name ? ` — ${name}` : ''}.`,
    draftProgress: (done: number, total: number) => (
      <>
        Jarayoningiz shu qurilmada saqlangan. <span className="num">{total}</span> bo'limdan{' '}
        <span className="num">{done}</span> tasini to'ldirdingiz — qoldirgan joyingizdan davom eting.
      </>
    ),
    continueCta: (stepTitle: string) => `Davom etish — ${stepTitle}`,
    emptyHeading: 'Startapingiz investitsiyaga loyiqmi — bilib olaylik.',
    emptyBody:
      "Biznesingiz haqida oltita halol savolga javob berasiz — muammo, mahsulot, bozor, natijalar, jamoa va so'rovingiz. Bu 20–30 daqiqa oladi, yozganingiz avtomatik saqlanadi va telefonda bemalol ishlaydi. Har bir topshirilgan startapni haqiqiy venchur hamkori o'qib, sizga haqqoniy xulosa yozadi.",
    submitCta: 'Startapingizni topshiring',
    afterHeading: "Topshirganingizdan keyin nima bo'ladi",
    afterFee: "Baholash to'lovi",
    afterFeeSub:
      "Bir martalik to'lov tahlil eshigini ochadi — u har bir topshirishni jiddiy qiladi, bizniki bilan birga.",
    afterPartner: 'Hamkor tahlili',
    afterPartnerSub:
      'AI standartlashtiradi, inson baholaydi. Aksariyat tahlillar besh ish kuni ichida tugaydi.',
    afterVerdict: 'Sizning xulosangiz',
    afterVerdictSub:
      "Sababi bilan aniq qaror — javob «hozircha yo'q» bo'lsa, uni nima o'zgartirishi ham.",
    submittedSummaryTitle: (name: string) => `Topshirilgan startapingiz — ${name}`,
    notFilled: "To'ldirilmagan.",
  },

  steps: {
    problem: {
      title: 'Muammo',
      question: 'Qanday muammoni va kim uchun hal qilasiz?',
      hint: "Aniq yozing: bu og'riqni kim, qanchalik tez-tez his qiladi va bu unga bugun qanchaga tushadi. Oddiy so'zlar pitch tilidan kuchliroq.",
      placeholder:
        "Masalan: Toshkentdagi restoranlar mahsulotni bozordan telefon qo'ng'irog'i va naqd pul bilan sotib oladi. Narxlar haftasiga 20% o'zgaradi va egalari qancha xarajat qilayotganini ko'ra olmaydi…",
    },
    product: {
      title: 'Mahsulot',
      question: 'Nima qurdingiz va u muammoni qanday hal qiladi?',
      hint: "Bugungi kunda haqiqatda mavjud narsani yozing — reja emas. Mijozlar undan qanday foydalanadi va siz qanday pul topasiz?",
      placeholder:
        "Masalan: Restoranlarni tekshirilgan ulgurji yetkazib beruvchilar bilan bog'laydigan buyurtma ilovasi. 22:00 gacha bitta buyurtma, 07:00 gacha yetkazma, bitta hisob-faktura. Biz 6% olamiz…",
    },
    market: {
      title: 'Bozor',
      question: 'Imkoniyat qanchalik katta?',
      hint: "Bozorni halol baholang, iloji bo'lsa quyidan yuqoriga hisoblab. Bu pul uchun yana kim raqobatlashadi — \"hech narsa qilmaslik\" ham shu jumlaga kiradi?",
      placeholder:
        "Masalan: Toshkentda 12 000 umumiy ovqatlanish korxonasi xaridga oyiga $8–15 ming sarflaydi — yiliga qariyb $600M lik oqim…",
    },
    traction: {
      title: 'Natijalar',
      question: 'Bu ishlayotganiga qanday isbotingiz bor?',
      hint: "Sifatlar emas, raqamlar: mijozlar, daromad, o'sish sur'ati, mijozlarning qolishi. Hali daromad bo'lmasa, ochiq ayting — halollik bo'rttirishdan yaxshiroq o'qiladi.",
      placeholder:
        "Masalan: 9 oydan beri ishlaymiz. 214 restoran har hafta buyurtma beradi. O'tgan oy GMV $412 000, oyiga 18% o'sish. Churn 3% dan past…",
    },
    team: {
      title: 'Jamoa',
      question: 'Buni kim qurmoqda va nega aynan siz?',
      hint: "Asoschilar, ularning tegishli tajribasi, kim to'liq stavkada ishlashi va ulushlar qanday taqsimlangani. Investorlar g'oyadan ko'ra jamoaga pul beradi.",
      placeholder:
        "Masalan: CEO besh yil kafelar tarmog'ining ta'minotini boshqargan; CTO Uzumda logistika marshrutlashini qurgan. Ikkalasi to'liq stavkada, birgalikda 82% ulush…",
    },
    ask: {
      title: "So'rov",
      question: 'Qancha jalb qilyapsiz va bu pul nimaga sarflanadi?',
      hint: "Summa, ulush va bu mablag' nimaga erishtirishi. Allaqachon kelishilgan investitsiyalarni ham ayting.",
      placeholder:
        "Masalan: Yana ikki shaharga kengayish va ikki savdo rahbarini yollash uchun 12% evaziga $500 000 seed jalb qilmoqdamiz. $180 000 allaqachon kelishilgan…",
    },
  } as Record<StepKey, { title: string; question: string; hint: string; placeholder: string }>,

  submit: {
    stepsNavAria: 'Topshirish bosqichlari',
    stepOf: (current: number, total: number) => `${total} bosqichdan ${current}-si`,
    startupName: 'Startap nomi',
    startupNamePlaceholder: 'Masalan: Xarid',
    oneLiner: 'Bir qatorli tavsif',
    oneLinerPlaceholder: "Masalan: Restoranlar uchun B2B ta'minot marketpleysi",
    sector: 'Soha',
    sectorPlaceholder: 'Masalan: Fintech, Logistika, EdTech',
    fundingStage: 'Moliyalash bosqichi',
    choose: 'Tanlang…',
    errName: "Davom etishdan oldin startap nomini kiriting va savolga javob bering.",
    errEmpty: "Davom etishdan oldin bu bo'limga javob bering — bo'sh bo'limni ko'rib chiqib bo'lmaydi.",
    revenue: "Oylik daromad (bo'lsa)",
    revenuePlaceholder: "Masalan: oyiga $24 700 — yoki «hali daromadsiz»",
    growth: "O'sish",
    growthPlaceholder: 'Masalan: oyiga +18%',
    askShort: 'Jalb qilinayotgan summa, qisqacha',
    askShortPlaceholder: 'Masalan: $500k seed',
    attachments: 'Ilovalar',
    attachmentsStub: 'Demo — fayllar faqat shu qurilmada saqlanadi',
    deckLabel: 'Pitch-dek (PDF, maks. 10 MB)',
    revenueProofLabel: 'Daromad isboti (PDF, maks. 10 MB)',
    dataroomLabel: 'Data room havolasi (URL)',
    dataroomPlaceholder: 'drive.google.com/data-room',
    addLink: "Havolani qo'shish",
    errPdfOnly: 'Faqat PDF fayl qabul qilinadi.',
    errFileTooLarge: 'Fayl hajmi 10 MB dan oshmasligi kerak.',
    errFileStore: "Faylni saqlab bo'lmadi — brauzer xotirasiga yozib bo'lmadi. Qayta urinib ko'ring.",
    errBadUrl: "To'g'ri http(s) havolasini kiriting.",
    removeAttachment: (label: string) => `${label} faylini olib tashlash`,
    remove: 'Olib tashlash',
    autosaved: "Shu qurilmada saqlandi — istalgan payt chiqib, keyin qaytishingiz mumkin.",
    autosaveIdle: 'Javoblaringiz yozganingiz sari avtomatik saqlanadi.',
    saveExit: 'Saqlash va chiqish',
    toPay: "To'lovga o'tish",
    next: 'Davom etish',
  },

  pay: {
    title: "Oxirgi qadam: baholash to'lovi",
    intro:
      "Aynan shu to'lov tahlilni jiddiy qiladi — u haqiqiy hamkorning vaqtini va qanday bo'lmasin haqqoniy javobni ta'minlaydi. To'lov yakunlanishi bilan startapingiz ko'rib chiqish pipeline'iga kiradi.",
    orderSummary: 'Buyurtma xulosasi',
    stubPayment: "Simulyatsiya qilingan to'lov — kartadan pul yechilmaydi",
    lineItem: (name: ReactNode) => (
      <>
        Startap baholovi — <strong>{name}</strong>
      </>
    ),
    totalDue: "Bugun to'lanadigan jami",
    cardNumber: 'Karta raqami',
    expiry: 'Amal muddati',
    cvc: 'CVC',
    declined:
      "Kartangiz rad etildi (simulyatsiya). Kiritgan ma'lumotlaringiz saqlanib turibdi — tayyor bo'lganingizda qayta urinib ko'ring.",
    processing: 'Bajarilmoqda…',
    payButton: (fee: string) => `${fee} to'lash va topshirish`,
    simulateDeclined: 'Rad etilgan kartani simulyatsiya qilish',
    backToSubmit: 'Topshirishga qaytish',
    backNote: "— to'lov yakunlanmaguncha hech narsa yuborilmaydi.",
    toastPaid: "To'lov qabul qilindi — startapingiz topshirildi.",
  },

  verdict: {
    decisionChip: (decision: string) => `Qaror: ${decision}`,
    heading: (name: string) => `${name} uchun xulosangiz`,
    reviewedLine: (date: string) =>
      `Hamkor tomonidan ko'rib chiqilgan va imzolangan · yuborildi ${date}`,
    langToggleAria: 'Xulosa tili',
    downloadLetter: 'Rasmiy xatni yuklab olish (PDF)',
    enAlways: 'Inglizcha asl nusxa har doim mavjud —',
    enView: "inglizcha asl nusxani ko'rish",
    questions: (link: ReactNode) => (
      <>
        Bu qaror bo'yicha savolingiz bormi? Hisobingizdagi emaildan javob yozing — hamkor o'z
        mulohazasini tushuntiradi. {link}
      </>
    ),
    backToStartup: 'Mening startapimga qaytish',
  },

  letter: {
    backToVerdict: '← Xulosaga qaytish',
    downloadPdf: 'PDF yuklab olish (chop etish orqali)',
    letterAria: 'Rasmiy xulosa xati',
    letterheadLine: (date: string) => `Rasmiy xulosa xati · ${date}`,
    footer: (id: string, name: string) =>
      `Raqam: ${id} · Ushbu xat ko'rib chiquvchi hamkorning ${name} startapi bo'yicha qarorini qayd etadi. Bevosita tomonidan Toshkentda berilgan.`,
  },

  account: {
    title: 'Hisob',
    prefLang: 'Afzal til',
    prefLangValue: "O'zbekcha (xulosalar o'z tilingizda keladi)",
    billing: "To'lovlar tarixi",
    billingStub: "Simulyatsiya qilingan to'lovlar",
    noPayments:
      "Hozircha to'lovlar yo'q. Topshirishni yakunlaganingizda baholash to'lovi shu yerda ko'rinadi.",
    paid: "· to'langan",
    failed: '· rad etilgan',
    demoHeading: 'Demo boshqaruvi',
    demoBody:
      "Qayta o'rnatish butun demoni — topshirgan startapingiz, to'lovlaringiz va investor pipeline'ini — dastlabki namunaviy holatiga qaytaradi.",
    resetConfirm: "Ha, hammasini qayta o'rnatish",
    resetButton: "Demo ma'lumotlarini qayta o'rnatish",
    toastReset: "Demo ma'lumotlari dastlabki holatiga qaytarildi.",
  },

  board: {
    title: 'Pipeline',
    countsAria: (counts: string) => `Bosqichlar bo'yicha soni: ${counts}`,
    searchAll: 'Barcha startaplarni qidirish →',
    emptyCol: "Hozircha bu yer bo'sh.",
    passedTitle: 'Rad etilgan',
    passedNote: (link: ReactNode) => (
      <>
        {' '}
        — doska faol ishlar uchun qolishi maqsadida yig'ilgan; to'liq tarix {link} bo'limida
      </>
    ),
    passedLink: 'Startaplar',
    passedEmpty: "Hozircha rad etilgan startaplar yo'q.",
  },

  list: {
    title: 'Startaplar',
    intro:
      "Doimiy arxiv — barcha topshirilgan arizalar, qidiruv bilan. Doska harakat uchun; bu yer topish uchun.",
    searchPlaceholder: 'Nomi, xulosasi, sohasi, asoschisi bo\'yicha qidiring…',
    searchAria: 'Startaplarni qidirish',
    filterStage: "Bosqich bo'yicha saralash",
    allStages: 'Barcha bosqichlar',
    filterSignal: "Signal bo'yicha saralash",
    allSignals: 'Barcha signallar',
    filterOutcome: "Natija bo'yicha saralash",
    allOutcomes: 'Barcha natijalar',
    outcome: {
      recommend: 'Tavsiya etilgan',
      advance: "AQShga yo'llangan",
      pass: 'Rad etilgan',
      undecided: 'Qaror qilinmagan',
    },
    sortLabel: 'Tartiblash',
    sortRecent: 'Avval yangilari',
    sortOldest: 'Avval eskilari',
    sortSignal: "Signal bo'yicha",
    sortName: "Nomi bo'yicha",
    count: (n: number) => `${n} ta startap`,
    emptyTitle: 'Hech narsa topilmadi',
    emptyBody: "Filtrlarni kamaytirib yoki kengroq qidiruv so'zi bilan urinib ko'ring.",
    colStartup: 'Startap',
    colSignal: 'Signal',
    colStage: 'Bosqich',
    colSubmitted: 'Topshirilgan',
    colRevenue: 'Daromad',
    colOutcome: 'Natija',
  },

  detail: {
    notFoundTitle: 'Startap topilmadi',
    notFoundBody: (link: ReactNode) => (
      <>U olib tashlangan yoki havola noto'g'ri bo'lishi mumkin. {link}</>
    ),
    backToPipeline: "Pipeline'ga qaytish",
    backLink: '← Pipeline',
    submittedLabel: 'topshirilgan:',
    retag: 'Signalni qayta belgilash',
    tabsAria: 'Shu sahifada',
    tabReview: 'Tahlil',
    tabVerify: 'Tekshiruv',
    tabDecide: 'Qaror',
    tabVerdict: 'Xulosa',
    sentBanner: (date: string, decision: string) =>
      `Xulosa asoschiga ${date} kuni yuborildi — natija sifatida ${decision} qayd etildi.`,
    suggestionNote: (signal: string) =>
      `Taklif: ${signal} — yuqoridagi teg esa sizniki, o'zgartirishingiz mumkin.`,
    metricRevenue: 'Daromad',
    metricGrowth: "O'sish",
    metricAsk: "So'rov",
    summaryHeading: 'AI qisqacha bayoni',
    rawHeading: 'Asoschining asl matni',
    rawNote: "so'zma-so'z — hech narsa yashirilmagan",
    verification: 'Tekshiruv',
    verifiedCount: (done: number, total: number) => `${done}/${total} tekshirildi`,
    verificationIntro: "Insonning dalil tekshiruvi — bu qarorga sizning nomingiz tikilgan.",
    decisionHeading: 'Qaror',
    decisionGroupAria: 'Qaror tanlang',
    decisionSub: {
      recommend: 'Hamkor investorlarga taqdim etish',
      advance: 'AQShda shaxsiy tanishtiruvni boshlash',
      pass: "Halol «yo'q», sababi bilan",
    } as Record<Decision, string>,
    notesLabel: "Qoralama yozuvlar — asoschiga hech qachon ko'rsatilmaydi",
    notesHint:
      "Qisqa va ochiq yozing; grammatikaga qaramang. «agar …» bilan boshlangan qatorlar «javobimizni nima o'zgartirishi mumkin» bo'limiga tushadi.",
    notesPlaceholder:
      "Masalan:\ndaromad tasdiqlandi, litsenziya himoyasi haqiqiy\njamoaning sotuv tomoni zaif\nagar tijorat rahbarini yollashsa qayta ko'raman",
    composeButton: 'Xulosa tayyorlash',
    recomposeButton: 'Yozuvlardan qayta tayyorlash',
    composeToast: 'Yozuvlaringizdan qoralama tayyorlandi.',
    composeGate: 'Xulosa tayyorlash uchun qaror tanlang va kamida bir qator yozuv yozing.',
    composerSent: 'Yuborilgan xulosa',
    composerDraft: 'Xulosa qoralamasi',
    editedTag: 'Siz tahrirlagansiz',
    fromNotesBadge: 'Yozuvlaringizdan tayyorlandi — rasmiy muallif sizsiz',
    draftLangAria: 'Qoralama tili',
    enOriginal: 'Inglizcha asl nusxa',
    founderLang: (langLabel: string) => `${langLabel} (asoschining tili)`,
    editLabel: 'Qoralamani shu yerda tahrirlang — siz aytmaguningizcha hech narsa yuborilmaydi',
    translationNote:
      'Tahrirlar inglizcha asl nusxada qilinadi; qayta tayyorlash bu tarjimani yozuvlaringizdan qaytadan yaratadi.',
    confirmSend: (founderName: string) => `Tasdiqlash — ${founderName}ga yuborish`,
    notNow: 'Hozir emas',
    sendVerdict: 'Xulosani yuborish',
    sendNote: (name: ReactNode, decision: ReactNode) => (
      <>
        Yuborish {name} kartasini <strong>{decision}</strong> bosqichiga o'tkazadi va natijani qayd
        etadi. Hech narsa avtomatik yuborilmaydi.
      </>
    ),
    sentToast: 'Xulosa yuborildi — asoschi xabardor qilindi (simulyatsiya).',
    composerEmptyHeading: 'Xulosa',
    composerEmptyBody: (composeLabel: ReactNode, founderFirst: string) => (
      <>
        Qaror qilib, yozuvlaringizni yozganingizdan so'ng <strong>{composeLabel}</strong> ularni{' '}
        {founderFirst}ning tilida toza, rasmiy xatga aylantiradi — siz ko'rib chiqasiz, tahrirlaysiz
        va yuborasiz. AI asoschi bilan hech qachon nazoratsiz gaplashmaydi.
      </>
    ),
    attachHeading: 'Ilovalar va havolalar',
    attachStub: 'Yuklangan fayllar shu qurilmada saqlanadi',
    noAttachments: 'Asoschi fayl biriktirmagan.',
    openFile: (fileName: string) => `${fileName} faylini ochish`,
    open: 'Ochish',
    openFailed: "Faylni ochib bo'lmadi — bu qurilmada saqlanmagan.",
    downloadFile: (fileName: string) => `${fileName} faylini yuklab olish`,
    download: 'Yuklab olish',
    downloadFailed: "Faylni yuklab olib bo'lmadi — bu qurilmada saqlanmagan.",
    openLink: 'Havolani ochish',
    kindLabel: {
      deck: 'taqdimot',
      dataroom: 'data room',
      revenue: 'daromad',
      other: 'boshqa',
    },
  },

  settings: {
    title: 'Sozlamalar',
    role: 'Rol',
    roleValue: "Ko'rib chiquvchi hamkor — O'zbekiston piloti",
    letters: 'Xulosa xatlari',
    demoOnly: "Demo — faqat ko'rsatish uchun",
    signature: 'Xatlardagi imzo',
    signatureValue: (name: string) => `${name} — Bevosita hamkori`,
    signatureHint: 'Siz yuboradigan har bir xulosa xatining imzo qismida chiqadi.',
    notifications: 'Bildirishnomalar',
    notifNew: "Pipeline'ga yangi arizalar tushganda",
    notifDigest: "«Yangi» ustunining kunlik xulosasi",
    notifReplies: 'Asoschi yuborilgan xulosaga javob berganda',
    demoHeading: 'Demo boshqaruvi',
    demoBody:
      "Qayta o'rnatish namunaviy pipeline'ni tiklaydi hamda demo asoschining arizasini va siz qabul qilgan qarorlarni o'chiradi.",
    resetConfirm: "Ha, hammasini qayta o'rnatish",
    resetButton: "Demo ma'lumotlarini qayta o'rnatish",
    toastReset: "Demo ma'lumotlari dastlabki holatiga qaytarildi.",
  },
}

export type Messages = typeof uz
