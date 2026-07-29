import type { Decision, Lang } from './types'

/**
 * The verdict composer. Deterministic by design: the same notes always
 * produce the same draft, so the VC can tweak notes and re-polish cheaply.
 * In production this is an LLM call; the contract (notes in, structured
 * reviewable draft out, nothing auto-sends) stays the same.
 */

const SHORTHAND: Array<[RegExp, string]> = [
  [/\bw\/o\b/gi, 'without'],
  [/\bw\//gi, 'with '],
  [/\bb\/c\b/gi, 'because'],
  [/\bbc\b/gi, 'because'],
  [/\bimo\b/gi, 'in our view'],
  [/\bimho\b/gi, 'in our view'],
  [/\btbh\b/gi, 'frankly'],
  [/\bdef\b/gi, 'clearly'],
  [/\besp\b/gi, 'especially'],
  [/\bvs\.?\b/gi, 'versus'],
  [/\brev\b/gi, 'revenue'],
  [/\bmkt\b/gi, 'market'],
  [/\bgtm\b/gi, 'go-to-market'],
  [/\bbiz\b/gi, 'business'],
  [/\byoy\b/gi, 'year over year'],
  [/\bmom\b/gi, 'month over month'],
  [/\barr\b/gi, 'ARR'],
  [/\bmrr\b/gi, 'MRR'],
  [/\bcac\b/gi, 'CAC'],
  [/\bltv\b/gi, 'LTV'],
  [/\bdont\b/gi, "don't"],
  [/\bcant\b/gi, "can't"],
  [/\bwont\b/gi, "won't"],
  [/\bisnt\b/gi, "isn't"],
  [/\bdoesnt\b/gi, "doesn't"],
  [/\bdidnt\b/gi, "didn't"],
  [/\bhasnt\b/gi, "hasn't"],
  [/\bthats\b/gi, "that's"],
  [/\btheres\b/gi, "there's"],
  [/\s&\s/g, ' and '],
]

/** Clean one rough line into a presentable sentence. */
export function polishLine(line: string): string {
  let s = line.trim().replace(/^[-*•]+\s*/, '')
  if (!s) return ''
  for (const [re, out] of SHORTHAND) s = s.replace(re, out)
  s = s.replace(/\s+/g, ' ').replace(/\s+([,.;:!?])/g, '$1').trim()
  s = s.charAt(0).toUpperCase() + s.slice(1)
  if (!/[.!?]$/.test(s)) s += '.'
  return s
}

/**
 * Split rough notes into polished bullets. Lines are the unit; a single
 * multi-sentence line is split into sentences. Lines starting with "agar"
 * (or Russian "если", or English "if" / "would reconsider") are routed to
 * the "what would change our answer" section instead of the reasons list.
 */
export function polishNotes(notes: string): { reasons: string[]; changers: string[] } {
  let lines = notes
    .split(/\n+/)
    .map((l) => l.trim())
    .filter(Boolean)
  if (lines.length === 1 && /[.!?]\s+\S/.test(lines[0])) {
    lines = lines[0].split(/(?<=[.!?])\s+/)
  }
  const reasons: string[] = []
  const changers: string[] = []
  for (const line of lines) {
    const polished = polishLine(line)
    if (!polished) continue
    if (/^(agar\b|если\b|if\b|would reconsider\b|reconsider if\b)/i.test(line.trim().replace(/^[-*•]+\s*/, ''))) {
      changers.push(polished)
    } else {
      reasons.push(polished)
    }
  }
  return { reasons, changers }
}

export const LANG_LABEL: Record<Lang, string> = {
  en: 'English',
  uz: "O'zbekcha",
  ru: 'Русский',
}

interface Frame {
  salutation: (founder: string) => string
  opening: (startup: string) => string
  decision: Record<Decision, (startup: string) => string>
  reasonsHeader: string
  changersHeader: string
  changersFallback: Record<Decision, string | null>
  nextStepsHeader: string
  nextSteps: Record<Decision, string | null>
  closing: string
  signoff: (vc: string) => string
  demoNote: string | null
}

const FRAMES: Record<Lang, Frame> = {
  en: {
    salutation: (f) => `Dear ${f},`,
    opening: (s) =>
      `Thank you for submitting ${s} for validation through Bevosita. We reviewed your materials in full — the summary below is our honest assessment, written to be useful rather than flattering.`,
    decision: {
      recommend: (s) =>
        `Our decision: we are recommending ${s}. Based on our review, we will put ${s} forward to our partner investors with a positive recommendation.`,
      advance: (s) =>
        `Our decision: we are advancing ${s} toward a US introduction. We believe ${s} is ready to be presented to our partners in the United States, and we will begin that introduction personally.`,
      pass: (s) =>
        `Our decision: we are passing at this time. After careful review, we have decided not to move ${s} forward right now. This is a decision about timing and readiness, not about you or the worth of your work.`,
    },
    reasonsHeader: 'Our reasoning',
    changersHeader: 'What would change our answer',
    changersFallback: {
      recommend: null,
      advance: null,
      pass: 'Meaningful progress on the points above — demonstrated in numbers, not plans — would be a reason to resubmit. We would genuinely welcome that.',
    },
    nextStepsHeader: 'Next steps',
    nextSteps: {
      recommend: 'We will share your materials with our partner network and contact you within ten business days with any interest.',
      advance: 'We will contact you within five business days to prepare the US introduction: expect a short call to align on materials and timing. The introduction itself happens person-to-person.',
      pass: null,
    },
    closing:
      'This verdict was written to be honest because your time and effort deserve honesty. If anything here is unclear, reply and we will explain our thinking.',
    signoff: (vc) => `With respect,\n${vc}\nPartner, Bevosita`,
    demoNote:
      "(Demo note: the reasons above are shown in the language of the partner's notes; the production version translates them fully.)",
  },
  uz: {
    salutation: (f) => `Hurmatli ${f},`,
    opening: (s) =>
      `${s} loyihangizni Bevosita orqali baholashga topshirganingiz uchun rahmat. Biz materiallaringizni to'liq ko'rib chiqdik — quyidagi xulosa xushomad uchun emas, foydali bo'lishi uchun halol yozildi.`,
    decision: {
      recommend: (s) =>
        `Qarorimiz: biz ${s} loyihasini tavsiya qilamiz. Ko'rib chiqish natijasida biz uni hamkor investorlarimizga ijobiy tavsiya bilan taqdim etamiz.`,
      advance: (s) =>
        `Qarorimiz: biz ${s} loyihasini AQShdagi hamkorlarimiz bilan tanishtirish bosqichiga o'tkazamiz va bu tanishtiruvni shaxsan boshlaymiz.`,
      pass: (s) =>
        `Qarorimiz: hozircha to'xtaymiz. Sinchiklab o'rganib chiqib, biz ${s} loyihasini ayni paytda oldinga surmaslikka qaror qildik. Bu — vaqt va tayyorgarlik haqidagi qaror; sizning mehnatingiz qadri haqida emas.`,
    },
    reasonsHeader: 'Sabablarimiz',
    changersHeader: "Javobimizni nima o'zgartirishi mumkin",
    changersFallback: {
      recommend: null,
      advance: null,
      pass: "Yuqoridagi bandlar bo'yicha real natija — reja emas, raqamlarda ko'ringan o'sish — qayta topshirish uchun asos bo'ladi. Bunga chin dildan xush kelibsiz.",
    },
    nextStepsHeader: 'Keyingi qadamlar',
    nextSteps: {
      recommend: "Materiallaringizni hamkorlar tarmog'imizga ulashamiz va o'n ish kuni ichida natija bo'yicha bog'lanamiz.",
      advance: "Besh ish kuni ichida siz bilan bog'lanib, AQSh tanishtiruviga tayyorgarlikni boshlaymiz: materiallar va vaqtni kelishish uchun qisqa qo'ng'iroq kutilmoqda.",
      pass: null,
    },
    closing:
      "Bu xulosa halol yozildi, chunki sizning vaqtingiz va mehnatingiz halollikka loyiq. Biror narsa tushunarsiz bo'lsa, javob yozing — fikrimizni tushuntiramiz.",
    signoff: (vc) => `Hurmat bilan,\n${vc}\nBevosita hamkori`,
    demoNote: null,
  },
  ru: {
    salutation: (f) => `Уважаемый(ая) ${f},`,
    opening: (s) =>
      `Спасибо, что представили ${s} на оценку через Bevosita. Мы полностью изучили ваши материалы — заключение ниже написано честно, чтобы быть полезным, а не лестным.`,
    decision: {
      recommend: (s) =>
        `Наше решение: мы рекомендуем ${s}. По итогам рассмотрения мы представим проект нашим партнёрам-инвесторам с положительной рекомендацией.`,
      advance: (s) =>
        `Наше решение: мы продвигаем ${s} к знакомству с нашими партнёрами в США и лично начнём это представление.`,
      pass: (s) =>
        `Наше решение: пока мы воздержимся. После внимательного рассмотрения мы решили не продвигать ${s} на данном этапе. Это решение о времени и готовности, а не о ценности вашей работы.`,
    },
    reasonsHeader: 'Наши причины',
    changersHeader: 'Что изменило бы наш ответ',
    changersFallback: {
      recommend: null,
      advance: null,
      pass: 'Реальный прогресс по пунктам выше — подтверждённый цифрами, а не планами — станет основанием подать заявку повторно. Мы будем этому искренне рады.',
    },
    nextStepsHeader: 'Следующие шаги',
    nextSteps: {
      recommend: 'Мы поделимся вашими материалами с сетью партнёров и свяжемся с вами в течение десяти рабочих дней.',
      advance: 'Мы свяжемся с вами в течение пяти рабочих дней, чтобы подготовить представление в США: короткий звонок для согласования материалов и сроков.',
      pass: null,
    },
    closing:
      'Это заключение написано честно, потому что ваше время и труд заслуживают честности. Если что-то неясно — ответьте, и мы объясним ход наших рассуждений.',
    signoff: (vc) => `С уважением,\n${vc}\nПартнёр Bevosita`,
    demoNote: '(Примечание демо: причины показаны на языке заметок партнёра; в рабочей версии письмо переводится полностью.)',
  },
}

export interface ComposeInput {
  decision: Decision
  notes: string
  startupName: string
  founderName: string
  vcName: string
  lang: Lang
  /** A stable date string, e.g. "28 July 2026". */
  dateLabel: string
}

/** Render the full verdict letter in one language. Pure and deterministic. */
export function composeVerdict(input: ComposeInput): string {
  const frame = FRAMES[input.lang]
  const { reasons, changers } = polishNotes(input.notes)
  const parts: string[] = []

  parts.push(frame.salutation(input.founderName))
  parts.push(frame.opening(input.startupName))
  parts.push(frame.decision[input.decision](input.startupName))

  if (reasons.length > 0) {
    const noteLine = frame.demoNote ? `\n${frame.demoNote}` : ''
    parts.push(`${frame.reasonsHeader}:\n${reasons.map((r) => `— ${r}`).join('\n')}${noteLine}`)
  }

  const changersBody =
    changers.length > 0
      ? changers.map((c) => `— ${c}`).join('\n')
      : frame.changersFallback[input.decision]
  if (changersBody) {
    parts.push(`${frame.changersHeader}:\n${changersBody}`)
  }

  const next = frame.nextSteps[input.decision]
  if (next) {
    parts.push(`${frame.nextStepsHeader}:\n${next}`)
  }

  parts.push(frame.closing)
  parts.push(`${frame.signoff(input.vcName)}\n${input.dateLabel}`)

  return parts.join('\n\n')
}
