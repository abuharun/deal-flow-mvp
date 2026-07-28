import { describe, expect, it } from 'vitest'
import { formatDate, formatDateLong } from '../lib/format'
import { localizeStartup } from '../lib/content'
import { seedStartups } from '../lib/seed'
import { opaqueId } from '../lib/simulate'
import { verdictTextFor } from '../lib/verdictText'

describe('localized dates', () => {
  it('formats short and long Russian dates without depending on host ICU data', () => {
    expect(formatDate('2026-07-26T09:40:00Z', 'ru')).toBe('26 июл. 2026')
    expect(formatDateLong('2026-07-26T09:40:00Z', 'ru')).toBe('26 июля 2026')
    expect(formatDate('2026-07-26T00:30:00Z', 'ru')).toBe('26 июл. 2026')
    expect(formatDate('not-a-date', 'ru')).toBe('—')
  })
})

describe('seeded content localization', () => {
  it('has a Russian display overlay for every seeded startup', () => {
    for (const canonical of seedStartups()) {
      const localized = localizeStartup(canonical, 'ru')
      expect(localized.oneLiner, canonical.name).not.toBe(canonical.oneLiner)
      expect(localized.raw.problem, canonical.name).toMatch(/[А-Яа-яЁё]/)
      expect(localized.recommendation.headline, canonical.name).toMatch(/[А-Яа-яЁё]/)
    }
  })

  it('dynamically overlays Russian content without mutating canonical state', () => {
    const canonical = seedStartups().find((startup) => startup.id === opaqueId('xarid'))!
    const localized = localizeStartup(canonical, 'ru')

    expect(localized.oneLiner).toBe('B2B-маркетплейс снабжения для ресторанов и кафе')
    expect(localized.raw.problem).toMatch(/^Рестораны Ташкента/)
    expect(localized.summary.problem).toMatch(/^Рестораны Ташкента/)
    expect(localized.metrics.revenue).toBe('$24.7k валовой / мес')
    expect(localizeStartup({ ...canonical, fundingStage: "Ko'rsatilmagan" }, 'ru').fundingStage).toBe('Не указано')
    expect(localized.verification[0].label).toBe('Подтверждение выручки соответствует заявлению')
    expect(localized.founder.city).toBe('Ташкент')
    expect(canonical.oneLiner).toBe("Restoran va kafelar uchun B2B ta'minot marketpleysi")
  })

  it('keeps verdict-body language independent from the interface locale', () => {
    const canonical = seedStartups().find((startup) => startup.id === opaqueId('solaruz'))!
    const localized = localizeStartup(canonical, 'ru')

    expect(localized.verdict).toBe(canonical.verdict)
    expect(verdictTextFor(localized, 'en')).toMatch(/^Dear Dilnoza Saidova,/)
    expect(verdictTextFor(localized, 'uz')).toMatch(/^Hurmatli Dilnoza Saidova,/)
    expect(verdictTextFor(localized, 'ru')).toMatch(/^Уважаемый\(ая\) Dilnoza Saidova,/)
  })
})