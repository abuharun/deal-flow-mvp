import type { Attachment, Decision, Lang, Signal, Stage, Startup, StepKey, VerificationItem } from './types'
import { summarizeField, opaqueId } from './simulate'
import { composeVerdict } from './compose'
import { formatDateLong } from './format'

/** The demo VC partner. One partner, one country — per the pilot scope. */
export const VC_NAME = 'Laylo Mirzaeva'
export const VC_EMAIL = 'laylo@oqim.demo'

/** The demo founder account. */
export const FOUNDER_NAME = 'Dilshod Ergashev'
export const FOUNDER_EMAIL = 'dilshod@oqim.demo'

export const VALIDATION_FEE = '$199'

export function makeVerification(): VerificationItem[] {
  return [
    { id: 'revenue', label: 'Revenue proof matches the claim', hint: 'Bank statement or payment-provider export', done: false },
    { id: 'captable', label: 'Cap table is clean', hint: 'Founder equity intact, no broken ownership', done: false },
    { id: 'references', label: 'Founder references check out', hint: 'Two independent references contacted', done: false },
    { id: 'registry', label: 'Company registration verified', hint: 'State registry lookup matches the filing', done: false },
  ]
}

interface SeedSpec {
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

const SPECS: SeedSpec[] = [
  {
    name: 'Xarid',
    oneLiner: 'B2B procurement marketplace for restaurants and cafés',
    sector: 'B2B Marketplace',
    fundingStage: 'Seed',
    founder: { name: 'Aziza Karimova', email: 'aziza@xarid.uz', city: 'Tashkent', language: 'uz' },
    submittedAt: '2026-07-26T09:40:00Z',
    stage: 'new',
    signal: 'high',
    raw: {
      problem:
        'Restaurants in Tashkent buy produce, meat and dry goods from Chorsu bazaar through personal relationships and cash. Prices swing 20% week to week, there are no receipts, and a chef spends two hours every morning calling suppliers. Owners cannot see what they actually spend.',
      product:
        'Xarid is an ordering app connecting restaurants to vetted wholesale suppliers. The restaurant places one order before 22:00; we consolidate across suppliers and deliver before 07:00 with a single itemized invoice. We take a 6% margin on the basket.',
      market:
        'There are roughly 12,000 registered food-service businesses in Tashkent alone and 40,000+ nationwide. Food procurement for a mid-size restaurant runs $8,000–15,000 per month. We estimate a $600M annual procurement flow in Tashkent.',
      traction:
        'Live for 9 months. 214 restaurants order at least weekly; 61 order daily. GMV last month was $412,000 with $24,700 gross revenue for us. Month-over-month GMV growth has averaged 18% for six months. Churn is under 3% monthly.',
      team:
        'Aziza Karimova (CEO) ran supply for the Bon! café chain for five years. Rustam Aliyev (CTO) built logistics routing at Uzum. Six staff total, three in the delivery-ops team. Both founders are full-time and hold 82% combined.',
      ask:
        'Raising $500,000 seed for 12% to expand to Samarkand and Bukhara, hire two sales leads, and build supplier-side inventory tooling. $180,000 committed from two local angels.',
    },
    metrics: { revenue: '$24.7k gross / mo', growth: '+18% GMV MoM', ask: '$500k seed' },
    recHeadline: 'Worth a close look soon',
    recRationale: [
      'Reported revenue and 18% monthly GMV growth are strong for this pipeline; verify against payment exports.',
      'Both founders have directly relevant domain experience; references should be straightforward to check.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'xarid-seed-deck.pdf' },
      { label: 'Revenue proof', kind: 'revenue', fileName: 'payme-export-jun.xlsx' },
      { label: 'Data room', kind: 'dataroom', fileName: 'drive.google.com/xarid-dataroom' },
    ],
  },
  {
    name: 'TezYol',
    oneLiner: 'Digital freight matching for long-haul trucking across Central Asia',
    sector: 'Logistics',
    fundingStage: 'Seed',
    founder: { name: 'Bekzod Rahimov', email: 'bekzod@tezyol.uz', city: 'Tashkent', language: 'ru' },
    submittedAt: '2026-07-25T14:10:00Z',
    stage: 'new',
    signal: 'high',
    raw: {
      problem:
        'A truck driving Tashkent to Almaty returns empty 40% of the time because freight matching happens over Telegram groups and phone calls with dispatchers taking 15–20% commission. Shippers cannot track cargo and drivers wait days to get paid.',
      product:
        'TezYol matches verified shippers with verified carriers, handles documents digitally, and pays the driver within 48 hours of proof of delivery — we take 8%. GPS tracking comes from a cheap dashboard phone mount and our driver app.',
      market:
        'Uzbekistan moves 60% of its trade by road. The domestic and cross-border trucking market is estimated at $2.1B annually. Fragmented: the largest fleet owner has under 200 trucks.',
      traction:
        'Launched 11 months ago. 1,840 registered drivers, 96 active shippers. Completed 3,100 shipments; last month 640 shipments and $92,000 in take. Growing 14% monthly. Kazakhstan corridor opened in May and is already 20% of volume.',
      team:
        'Bekzod Rahimov (CEO) was operations director at a 120-truck fleet. Elyor G‘aniyev (CTO) ex-EPAM. Nine people. Founders hold 74%.',
      ask:
        'Raising $750,000 for 15% to fund the driver fast-payment float, expand the Kazakhstan corridor, and hire a compliance lead for cross-border documents.',
    },
    metrics: { revenue: '$92k take / mo', growth: '+14% MoM', ask: '$750k seed' },
    recHeadline: 'Worth a close look soon',
    recRationale: [
      'Volume and revenue figures are substantial; the fast-payment float is the main financial risk to probe.',
      'Cross-border expansion claims should be checked against actual Kazakhstan shipment records.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'tezyol-deck-v4.pdf' },
      { label: 'Revenue proof', kind: 'revenue', fileName: 'shipments-ledger-2026.xlsx' },
    ],
  },
  {
    name: 'BilimPay',
    oneLiner: 'Installment financing for professional courses and bootcamps',
    sector: 'Fintech · EdTech',
    fundingStage: 'Pre-seed',
    founder: { name: 'Nodira Yusupova', email: 'nodira@bilimpay.uz', city: 'Tashkent', language: 'uz' },
    submittedAt: '2026-07-24T08:05:00Z',
    stage: 'new',
    signal: 'medium',
    raw: {
      problem:
        'IT bootcamps in Tashkent cost $800–1,500 up front — three to five months of an average salary. Banks will not finance course fees, so schools lose half their qualified applicants at the payment step.',
      product:
        'BilimPay lets a student split tuition over 6–12 months. We pay the school up front minus a 9% discount and collect from the student. Underwriting uses employment status, a guarantor, and the school completion-rate data we collect.',
      market:
        'An estimated 90,000 people in Uzbekistan pay for professional courses annually, roughly a $70M tuition market and growing fast with IT-park tax incentives.',
      traction:
        'Piloting with 4 schools for 5 months. 312 loans issued, $214,000 originated. Default rate so far 4.1%, but the oldest cohort is only five months in. Two schools asked to expand to all their intakes.',
      team:
        'Nodira Yusupova (CEO) was a credit-risk analyst at Kapitalbank for six years. Hiring a CTO — the product currently runs on a contracted development shop. Founder holds 95%.',
      ask:
        'Raising $300,000 pre-seed for 10%, mainly for the lending book and the first in-house engineering hires.',
    },
    metrics: { revenue: '$214k originated', growth: '4 school pilots', ask: '$300k pre-seed' },
    recHeadline: 'Promising, with open questions',
    recRationale: [
      'Origination volume is real, but default data is too young to trust — treat the 4.1% figure as provisional.',
      'No technical co-founder; the outsourced build is a risk worth raising directly.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'bilimpay-preseed.pdf' },
      { label: 'Loan-book export', kind: 'revenue', fileName: 'loan-tape-jul.csv' },
    ],
  },
  {
    name: 'Navbat',
    oneLiner: 'Appointment and queue management for private clinics',
    sector: 'HealthTech SaaS',
    fundingStage: 'Pre-seed',
    founder: { name: 'Malika Azimova', email: 'malika@navbat.uz', city: 'Samarkand', language: 'ru' },
    submittedAt: '2026-07-22T11:30:00Z',
    stage: 'new',
    signal: 'medium',
    raw: {
      problem:
        'Private clinics in Uzbekistan book patients by phone into paper journals. Double-bookings and no-shows waste roughly a fifth of doctor hours, and patients queue in hallways for hours with no visibility.',
      product:
        'A clinic-side scheduling dashboard plus a patient Telegram bot for booking, reminders, and live queue position. Clinics pay $49/month per location. Setup takes one afternoon and works on the receptionist’s existing computer.',
      market:
        'Around 6,500 licensed private clinics in Uzbekistan; we can reach 2,000 of them in the four largest cities. At $49/month that is a $3.8M serviceable market — small alone, but the wedge into clinic payments and records.',
      traction:
        '38 paying clinics after 7 months, $1,860 MRR, about 9% monthly growth. No-show rates at our clinics dropped from 22% to 9%. Churned 3 clinics, all single-doctor practices.',
      team:
        'Malika Azimova (CEO) managed operations for a 3-clinic dental group. Aibek Salimov (CTO) built the product solo, ex-freelancer. Both full-time, 100% founder-owned.',
      ask:
        'Raising $150,000 for 8% to hire two sales reps for Tashkent and build the payments module clinics keep asking for.',
    },
    metrics: { revenue: '$1.9k MRR', growth: '+9% MoM', ask: '$150k pre-seed' },
    recHeadline: 'Promising, with open questions',
    recRationale: [
      'Retention and the measured no-show improvement are genuine signal at this scale.',
      'The stated SaaS market is small; the payments wedge is the venture case — probe how real it is.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [{ label: 'Pitch deck', kind: 'deck', fileName: 'navbat-deck.pdf' }],
  },
  {
    name: 'AgroSensor',
    oneLiner: 'Soil-moisture sensors and irrigation advice for cotton farms',
    sector: 'AgriTech',
    fundingStage: 'Pre-seed',
    founder: { name: 'Jasur Toshpulatov', email: 'jasur@agrosensor.uz', city: 'Fergana', language: 'uz' },
    submittedAt: '2026-07-20T16:45:00Z',
    stage: 'new',
    signal: 'low',
    raw: {
      problem:
        'Cotton farms over-irrigate by 30–40% because watering follows fixed schedules, not soil data. Water quotas are tightening every year and the Aral basin restrictions will make flood irrigation economically impossible within a decade.',
      product:
        'A LoRa soil-moisture probe we assemble locally for $60 in parts, plus an SMS advisory service telling the farm manager when and how much to irrigate. We have built 25 prototype units and run one field trial on a partner farm.',
      market:
        'Uzbekistan has about 1M hectares under cotton across roughly 80,000 farming units, mostly state-quota clusters. Selling requires cluster-level or government contracts.',
      traction:
        'One completed field trial on 40 hectares showed 24% water reduction with no yield loss — strong result, but a single season on a single farm. No revenue yet. Two clusters signed letters of interest, not contracts.',
      team:
        'Jasur Toshpulatov (CEO) is an irrigation engineer, PhD from TIIAME. Working alone with two part-time students. Currently employed part-time at the institute.',
      ask:
        'Raising $200,000 for 15% to manufacture 500 units and run three paid cluster pilots for the 2027 season.',
    },
    metrics: { revenue: 'Pre-revenue', growth: '1 field trial', ask: '$200k pre-seed' },
    recHeadline: 'Likely early for this pipeline',
    recRationale: [
      'No commercial traction is reported yet; the case rests on one field trial and letters of interest.',
      'Solo, part-time founder selling into government-linked clusters is a hard combination — ask about full-time commitment.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'agrosensor-deck.pdf' },
      { label: 'Field-trial report', kind: 'other', fileName: 'trial-report-2026.pdf' },
    ],
  },
  {
    name: 'OshMarket',
    oneLiner: '30-minute grocery delivery from neighborhood dark stores',
    sector: 'Consumer · Q-commerce',
    fundingStage: 'Seed',
    founder: { name: 'Sardor Umarov', email: 'sardor@oshmarket.uz', city: 'Tashkent', language: 'uz' },
    submittedAt: '2026-07-17T10:20:00Z',
    stage: 'in-review',
    signal: 'medium',
    raw: {
      problem:
        'Working families in Tashkent’s new residential districts are far from bazaars and big supermarkets. Existing delivery apps take 2–4 hours and substitute items without asking.',
      product:
        'Three dark stores of 1,200 SKUs each, our own couriers on electric mopeds, 30-minute promise inside a 3km radius. Average basket $14, delivery fee $0.90, blended contribution margin currently −$0.40 per order.',
      market:
        'Tashkent metro area has 3M people; the districts we target hold 600,000 residents with above-average income. Grocery is a $1.5B market in the city.',
      traction:
        '5,400 monthly active customers, 31,000 orders last month, $430,000 GMV. Orders grow 11% monthly. Unit economics are negative and improving: contribution margin was −$1.10 four months ago.',
      team:
        'Sardor Umarov (CEO) previously launched Wolt operations in two Kazakh cities. Strong ops bench of four city managers. CTO is a technical lead promoted from within.',
      ask:
        'Raising $1.2M seed for 18% to reach contribution-margin breakeven at 8 stores and prove the model before a Series A.',
    },
    metrics: { revenue: '$430k GMV / mo', growth: '+11% MoM, CM −$0.40', ask: '$1.2M seed' },
    recHeadline: 'Promising, with open questions',
    recRationale: [
      'Scale and growth are real, but every order still loses money — the margin trajectory is the whole question.',
      'Category has burned capital globally; ask what is structurally different here.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'oshmarket-seed.pdf' },
      { label: 'Unit-economics model', kind: 'other', fileName: 'ue-model-jul.xlsx' },
      { label: 'Data room', kind: 'dataroom', fileName: 'notion.so/oshmarket-dr' },
    ],
    verifiedIds: ['registry'],
  },
  {
    name: 'KassaBox',
    oneLiner: 'Point-of-sale and automated tax compliance for small retailers',
    sector: 'Fintech SaaS',
    fundingStage: 'Seed',
    founder: { name: 'Timur Ibragimov', email: 'timur@kassabox.uz', city: 'Tashkent', language: 'ru' },
    submittedAt: '2026-07-15T09:00:00Z',
    stage: 'in-review',
    signal: 'high',
    raw: {
      problem:
        'Every retail point in Uzbekistan is legally required to run an online fiscal cash register, but the certified devices are clunky and the tax-report workflow still costs shops an accountant day per month. Fines for mistakes are severe.',
      product:
        'An Android app turning any $80 phone into a certified fiscal register, with tax reports filed automatically. $12/month per point of sale. We hold one of four fiscal-operator licenses issued by the tax committee.',
      market:
        'Roughly 450,000 registered retail points must comply. At $12/month the reachable market is about $45M ARR. The license is a moat: the queue for new ones is over two years.',
      traction:
        '6,800 paying points of sale, $79,000 MRR, growing 12% monthly for the last eight months. Net revenue retention 104%. Distribution through 40 accounting-firm partners who resell us to their clients.',
      team:
        'Timur Ibragimov (CEO) previously built and sold an accounting-software firm. CTO and CFO worked with him there. Fourteen staff. Founders hold 68% after an angel round.',
      ask:
        'Raising $900,000 seed for 12% to add payroll compliance and expand the accountant-partner channel nationally.',
    },
    metrics: { revenue: '$79k MRR', growth: '+12% MoM, NRR 104%', ask: '$900k seed' },
    recHeadline: 'Worth a close look soon',
    recRationale: [
      'Strong recurring revenue with a regulatory moat; the license claim is checkable and central — verify it.',
      'Repeat founder with a prior exit in the same domain; references should be fast.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'kassabox-seed-v2.pdf' },
      { label: 'Revenue proof', kind: 'revenue', fileName: 'mrr-export-jul.csv' },
      { label: 'Fiscal-operator license', kind: 'other', fileName: 'license-scan.pdf' },
    ],
    verifiedIds: ['registry', 'revenue'],
    notes: 'license moat looks real, checked registry\nrev export matches claimed mrr within 2%\nstill need 2 partner refs from the accounting channel',
  },
  {
    name: 'SolarUz',
    oneLiner: 'Financed rooftop solar for small factories and farms',
    sector: 'ClimateTech',
    fundingStage: 'Seed',
    founder: { name: 'Dilnoza Saidova', email: 'dilnoza@solaruz.uz', city: 'Tashkent', language: 'uz' },
    submittedAt: '2026-07-02T13:15:00Z',
    stage: 'recommended',
    signal: 'high',
    raw: {
      problem:
        'Small factories pay rising commercial electricity tariffs and suffer outages that stop production. Rooftop solar pays for itself in four years here, but no bank will finance it for a small business.',
      product:
        'We install rooftop solar at zero upfront cost and sell the electricity to the host under a 7-year power-purchase agreement priced 15% below grid tariff. After payback, we split further savings.',
      market:
        'Uzbekistan targets 25% renewable generation by 2030 with direct subsidies for distributed solar. We estimate 18,000 suitable commercial rooftops; average installation $40,000.',
      traction:
        '23 installations operating, $1.1M deployed, $31,000 monthly recurring electricity revenue, zero payment defaults in 14 months. Pipeline of 61 signed letters of intent. Panel supply contracted with two Chinese manufacturers.',
      team:
        'Dilnoza Saidova (CEO) financed energy projects at the ADB for seven years. CTO ran industrial electrical installation for a decade. Eleven staff, three licensed installation crews.',
      ask:
        'Raising $2M ($800k equity for 10%, $1.2M debt facility) to fund the next 45 installations.',
    },
    metrics: { revenue: '$31k recurring / mo', growth: '23 sites, 0 defaults', ask: '$2M (equity+debt)' },
    recHeadline: 'Worth a close look soon',
    recRationale: [
      'Recurring revenue with zero defaults across 14 months is exceptional signal in this pipeline.',
      'The model is capital-heavy; the equity/debt split and PPA enforceability deserve real scrutiny.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'solaruz-seed.pdf' },
      { label: 'Revenue proof', kind: 'revenue', fileName: 'ppa-receipts-h1.xlsx' },
      { label: 'Data room', kind: 'dataroom', fileName: 'drive.google.com/solaruz-dr' },
    ],
    verifiedIds: ['registry', 'revenue', 'references', 'captable'],
    decision: 'recommend',
    notes:
      'best asset-backed deal in the pipe, rev verified against ppa receipts\nceo is the strongest founder ive met this quarter, adb background shows\nppa contract enforceability is the open legal q but local counsel says its fine\nif the debt facility falls through the equity alone doesnt fund the plan',
    verdictSentAt: '2026-07-10T15:00:00Z',
  },
  {
    name: 'DoriGo',
    oneLiner: 'Licensed pharmacy delivery with cold-chain for insulin and biologics',
    sector: 'HealthTech',
    fundingStage: 'Seed',
    founder: { name: 'Kamola Rashidova', email: 'kamola@dorigo.uz', city: 'Tashkent', language: 'en' },
    submittedAt: '2026-06-20T10:00:00Z',
    stage: 'advanced',
    signal: 'high',
    raw: {
      problem:
        'Patients with diabetes and chronic conditions in Uzbekistan travel across town to find medicines in stock, and cold-chain drugs like insulin are frequently spoiled by improper storage. There is no legal delivery option for prescription medicines.',
      product:
        'DoriGo is the first licensed pharmacy-delivery operator in the country: we hold the pharmacy license, run validated cold-chain couriers, and integrate with 120 partner pharmacies for inventory. Prescriptions are verified by our staff pharmacists in-app.',
      market:
        'The retail pharmaceutical market in Uzbekistan is $1.8B and 70% of it is chronic-condition refills — exactly the recurring behavior delivery captures. Regional expansion to Kazakhstan doubles the market.',
      traction:
        '28,000 monthly orders, $610,000 GMV monthly, 19% take rate. 62% of orders are recurring refills. Growing 16% monthly. The health ministry cited us in its digital-health strategy.',
      team:
        'Kamola Rashidova (CEO) is a pharmacist with an MBA from INSEAD; she previously led pharma distribution for a regional wholesaler. CTO ex-Yandex. Twenty-two staff including six licensed pharmacists.',
      ask:
        'Raising $1.5M seed for 14% to expand to five more cities and begin the Kazakhstan licensing process. Interested in US investors for the Series A path.',
    },
    metrics: { revenue: '$116k take / mo', growth: '+16% MoM, 62% recurring', ask: '$1.5M seed' },
    recHeadline: 'Worth a close look soon',
    recRationale: [
      'Licensed moat plus recurring refill behavior is the strongest structural story in the current pipeline.',
      'Founder is explicitly seeking the US path; fit for the Advance track if verification holds.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [
      { label: 'Pitch deck', kind: 'deck', fileName: 'dorigo-seed.pdf' },
      { label: 'Revenue proof', kind: 'revenue', fileName: 'orders-gmv-export.xlsx' },
      { label: 'Pharmacy license', kind: 'other', fileName: 'dorigo-license.pdf' },
      { label: 'Data room', kind: 'dataroom', fileName: 'drive.google.com/dorigo-dr' },
    ],
    verifiedIds: ['registry', 'revenue', 'references', 'captable'],
    decision: 'advance',
    notes:
      'this is the one, license + cold chain is a real moat and rev checks out\nfounder presents at a us standard already, insead + pharma distribution\nrefs from two pharma wholesalers both glowing\nkz expansion makes the series a story continental not local',
    verdictSentAt: '2026-07-01T11:30:00Z',
  },
  {
    name: 'Mahalla',
    oneLiner: 'Neighborhood super-app for community services and payments',
    sector: 'Consumer Social',
    fundingStage: 'Pre-seed',
    founder: { name: 'Otabek Nazarov', email: 'otabek@mahalla.app', city: 'Tashkent', language: 'uz' },
    submittedAt: '2026-06-28T12:00:00Z',
    stage: 'passed',
    signal: 'low',
    raw: {
      problem:
        'Mahalla committees coordinate everything from utility issues to weddings through paper notices and word of mouth. Young residents are disconnected from their neighborhood institutions.',
      product:
        'A super-app for neighborhoods: announcements, local services marketplace, utility payments, and community chat. We plan to monetize through payment fees and local business listings once we reach scale.',
      market:
        'There are 9,000+ mahallas covering effectively the whole population of Uzbekistan — 36M people. If we become the default channel, the payments volume alone is billions.',
      traction:
        'Launched 4 months ago in 12 mahallas. 3,400 registered users, about 400 weekly actives. No revenue yet; monetization starts at scale. A government partnership discussion is ongoing.',
      team:
        'Otabek Nazarov (CEO), second-time founder — previous social app reached 50k downloads before shutting down. Two junior developers. Working from a government innovation-hub grant.',
      ask:
        'Raising $250,000 for 12% to expand to 200 mahallas and hire a growth lead.',
    },
    metrics: { revenue: 'Pre-revenue', growth: '400 WAU', ask: '$250k pre-seed' },
    recHeadline: 'Likely early for this pipeline',
    recRationale: [
      'No revenue and weekly actives are low relative to registrations; engagement is the open question.',
      'Super-app scope this early usually signals unfocused product; ask what the single wedge is.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [{ label: 'Pitch deck', kind: 'deck', fileName: 'mahalla-deck.pdf' }],
    verifiedIds: ['registry'],
    decision: 'pass',
    notes:
      'engagement is weak, 12% wau/reg after 4 months, thats a leaky product\nsuper app scope w/ 3 people isnt credible, no single wedge\nfounder is energetic and coachable tho, good instincts on community\nif they focus on one service and get to 40% wau id look again\nif utility payments alone show real repeat usage, reconsider',
    verdictSentAt: '2026-07-08T09:45:00Z',
  },
  {
    name: 'Chevar',
    oneLiner: 'Made-to-order marketplace for custom tailoring and traditional wear',
    sector: 'Consumer Marketplace',
    fundingStage: 'Pre-seed',
    founder: { name: 'Gulnora Vahidova', email: 'gulnora@chevar.uz', city: 'Bukhara', language: 'ru' },
    submittedAt: '2026-07-27T07:55:00Z',
    stage: 'new',
    signal: 'low',
    raw: {
      problem:
        'Custom tailoring is a huge informal economy in Uzbekistan — wedding season alone keeps thousands of ateliers booked for months — but finding a good tailor is pure word of mouth and pricing is opaque.',
      product:
        'A marketplace where customers browse tailor portfolios, get fixed quotes, and pay through escrow released on fitting approval. We take 10%. An early idea: standardized measurement kits shipped to the customer.',
      market:
        'We estimate the custom-clothing market at $400M annually, concentrated around weddings and holidays. No digital player exists.',
      traction:
        'Launched 6 weeks ago. 46 tailors onboarded, 28 completed orders, $2,100 GMV. Too early for cohorts. Instagram following of 18,000 built organically in two months.',
      team:
        'Gulnora Vahidova (CEO) ran a 6-person atelier for eight years and is a known name in Bukhara tailoring. No technical co-founder; the site is built on a no-code platform.',
      ask:
        'Raising $120,000 for 10% to hire a developer, build the escrow flow properly, and expand to Tashkent before wedding season.',
    },
    metrics: { revenue: '$2.1k GMV total', growth: '6 weeks live', ask: '$120k pre-seed' },
    recHeadline: 'Likely early for this pipeline',
    recRationale: [
      'Six weeks of data is not evaluable traction; the organic audience is the only distribution signal.',
      'Domain-credible founder without technical capacity — the platform risk is immediate.',
      'This is a starting point for your review, not an assessment of the business itself.',
    ],
    attachments: [{ label: 'Pitch deck', kind: 'deck', fileName: 'chevar-intro.pdf' }],
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
            dateLabel: formatDateLong(spec.verdictSentAt),
          }),
          local: composeVerdict({
            decision: spec.decision,
            notes: spec.notes ?? '',
            startupName: spec.name,
            founderName: spec.founder.name,
            vcName: VC_NAME,
            lang: spec.founder.language,
            dateLabel: formatDateLong(spec.verdictSentAt),
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
  return SPECS.map(buildStartup)
}
