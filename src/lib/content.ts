import type { Startup, StepKey } from './types'
import { STEP_KEYS } from './types'
import type { Locale } from '../i18n'
import { SEED_RU, type SeedRuEntry } from './seedRu'
import { SEED_SPECS } from './seed'
import { opaqueId, summarizeField } from './simulate'

/**
 * The Russian display layer for content that lives in state as Uzbek strings.
 *
 * State stays single-source (one Startup per startup, Uzbek canonical values);
 * `localizeStartup` overlays Russian at render time. Three kinds of content
 * are covered:
 *  - seeded startups: full hand-written translations from seedRu.ts,
 *    keyed by the seed's stable id;
 *  - generated/fallback strings (simulated-AI recommendations, "not
 *    specified" markers): translated by exact-match lookup, which also
 *    covers the demo founder's own submission;
 *  - free-typed founder text: left untouched — it is the founder's own
 *    words, and the product never rewrites those silently.
 */

interface SeedRuById {
  ru: SeedRuEntry
  /** Original Uzbek notes, to detect whether the VC has edited them. */
  uzNotes: string
}

const RU_BY_ID: Record<string, SeedRuById> = {}
for (const spec of SEED_SPECS) {
  const ru = SEED_RU[spec.name]
  if (ru) RU_BY_ID[opaqueId(spec.name.toLowerCase())] = { ru, uzNotes: spec.notes ?? '' }
}

/** Known generated or fallback Uzbek strings → Russian (exact match). */
const KNOWN_RU: Record<string, string> = {
  // simulate.ts recommendation headlines
  "Tez orada sinchiklab ko'rishga arziydi": 'Стоит присмотреться в ближайшее время',
  'Istiqbolli, ammo ochiq savollar bor': 'Перспективно, но есть открытые вопросы',
  "Bu pipeline uchun hali erta ko'rinadi": 'Для этого пайплайна выглядит рановато',
  // simulate.ts rationale lines
  "Asoschi tijoriy natijalar haqida yozgan; daromad da'vosini isbot bilan solishtiring.":
    'Основатель пишет о коммерческих результатах; сверьте заявленную выручку с доказательствами.',
  "Hali tijoriy natija ko'rsatilmagan; asosiy tayanch — bozor va jamoa.":
    'Коммерческого результата пока не показано; главная опора — рынок и команда.',
  "Jamoa bo'limi mazmunli yozilgan — tekshiruv bosqichida tavsiyalarni tekshiring.":
    'Раздел о команде написан содержательно — проверьте рекомендации на этапе проверки.',
  "Jamoa bo'limi juda qisqa; kim qurishini va kim sotishini so'rang.":
    'Раздел о команде слишком короткий; спросите, кто строит и кто продаёт.',
  "Bu ko'rib chiqishingiz uchun boshlang'ich nuqta — biznesning o'ziga berilgan baho emas.":
    'Это отправная точка для вашего разбора, а не оценка самого бизнеса.',
  // simulate.ts empty-field marker
  "Asoschi tomonidan to'ldirilmagan.": 'Не заполнено основателем.',
  // store.ts submission fallbacks
  'Nomsiz startap': 'Стартап без названия',
  'Bir qatorli tavsif kiritilmagan': 'Описание одной строкой не указано',
  "Ko'rsatilmagan": 'Не указано',
}

const VERIFICATION_RU: Record<string, { label: string; hint: string }> = {
  revenue: {
    label: 'Подтверждение выручки соответствует заявлению',
    hint: 'Банковская выписка или выгрузка платёжного провайдера',
  },
  captable: {
    label: 'Таблица капитализации (cap table) чистая',
    hint: 'Доля основателей цела, структура владения не нарушена',
  },
  references: {
    label: 'Рекомендации об основателе подтверждены',
    hint: 'Связались с двумя независимыми рекомендателями',
  },
  registry: {
    label: 'Регистрация компании проверена',
    hint: 'Данные государственного реестра совпадают с документами',
  },
}

/** Attachment display labels (labels are stored canonically in Uzbek). */
const ATTACH_LABEL_RU: Record<string, string> = {
  'Pitch-dek': 'Питч-дек',
  'Daromad isboti': 'Подтверждение выручки',
  'Data room': 'Data room',
  'Data room havolasi': 'Ссылка на data room',
  'Kredit portfeli eksporti': 'Выгрузка кредитного портфеля',
  'Yunit-ekonomika modeli': 'Модель юнит-экономики',
  'Fiskal operator litsenziyasi': 'Лицензия фискального оператора',
  'Dala sinovi hisoboti': 'Отчёт о полевом испытании',
  'Dorixona litsenziyasi': 'Аптечная лицензия',
}

const CITY_RU: Record<string, string> = {
  Toshkent: 'Ташкент',
  Samarqand: 'Самарканд',
  Buxoro: 'Бухара',
  "Farg'ona": 'Фергана',
}

function tr(value: string): string {
  return KNOWN_RU[value] ?? value
}

/**
 * Return the startup as it should be displayed in the given interface locale.
 * Pure and display-only: state, ids, and reducer contracts are untouched.
 * Verdict letters are deliberately NOT localized here — the verdict body's
 * language is the founder-facing selector's concern (uz|ru|en).
 */
export function localizeStartup(startup: Startup, locale: Locale): Startup {
  if (locale !== 'ru') return startup
  const entry = RU_BY_ID[startup.id]
  const ru = entry?.ru

  let summary: Record<StepKey, string>
  if (ru) {
    // The simulated AI summary is derived from the raw text, so the Russian
    // summary is derived from the Russian raw text by the same pure function.
    summary = {} as Record<StepKey, string>
    for (const k of STEP_KEYS) summary[k] = summarizeField(ru.raw[k])
  } else {
    summary = {} as Record<StepKey, string>
    for (const k of STEP_KEYS) summary[k] = tr(startup.summary[k])
  }

  return {
    ...startup,
    oneLiner: ru?.oneLiner ?? tr(startup.oneLiner),
    sector: ru?.sector ?? tr(startup.sector),
    fundingStage: tr(startup.fundingStage),
    raw: ru?.raw ?? startup.raw,
    summary,
    metrics: ru?.metrics ?? {
      revenue: tr(startup.metrics.revenue),
      growth: tr(startup.metrics.growth),
      ask: tr(startup.metrics.ask),
    },
    recommendation: ru
      ? { ...startup.recommendation, headline: ru.recHeadline, rationale: ru.recRationale }
      : {
          ...startup.recommendation,
          headline: tr(startup.recommendation.headline),
          rationale: startup.recommendation.rationale.map(tr),
        },
    attachments: startup.attachments.map((a) => ({ ...a, label: ATTACH_LABEL_RU[a.label] ?? a.label })),
    verification: startup.verification.map((v) => ({ ...v, ...(VERIFICATION_RU[v.id] ?? {}) })),
    founder: { ...startup.founder, city: CITY_RU[startup.founder.city] ?? startup.founder.city },
    // Seeded demo notes are shown in Russian only while the VC hasn't edited
    // them; the moment they're edited the state value wins verbatim.
    notes: ru?.notes !== undefined && startup.notes === entry.uzNotes ? ru.notes : startup.notes,
  }
}

/** Attachment labels are stored canonically in Uzbek; localize for display. */
export function attachmentLabel(label: string, locale: Locale): string {
  return locale === 'ru' ? ATTACH_LABEL_RU[label] ?? label : label
}

/** Payment labels are stored in Uzbek; swap the fixed prefix for display. */
export function localizePaymentLabel(label: string, locale: Locale): string {
  if (locale !== 'ru') return label
  return label
    .replace(/^Baholash to'lovi — /, 'Плата за оценку — ')
    .replace(/— ariza$/, '— заявка')
}
