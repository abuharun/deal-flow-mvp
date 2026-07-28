import { describe, expect, it } from 'vitest'
import { composeVerdict, polishLine, polishNotes, type ComposeInput } from './compose'

const BASE: ComposeInput = {
  decision: 'pass',
  notes: 'engagement is weak imo\nteam is thin w/ no sales lead\nif they hire a commercial lead id look again',
  startupName: 'Mahalla',
  founderName: 'Otabek Nazarov',
  vcName: 'Laylo Mirzaeva',
  lang: 'en',
  dateLabel: '8 July 2026',
}

const BASE_UZ_NOTES =
  "jalb etilganlik zaif\njamoada sotuv rahbari yo'q\nagar tijorat rahbarini yollashsa qayta ko'raman"

describe('polishLine', () => {
  it('expands shorthand, capitalizes, and punctuates', () => {
    expect(polishLine('- rev is real w/ receipts')).toBe('Revenue is real with receipts.')
    expect(polishLine('imo mkt is small')).toBe('In our view market is small.')
    expect(polishLine('cant scale b/c ops')).toBe("Can't scale because ops.")
  })

  it('capitalizes and punctuates Uzbek notes untouched by shorthand', () => {
    expect(polishLine('daromad haqiqiy, isbot bor')).toBe('Daromad haqiqiy, isbot bor.')
  })

  it('keeps existing terminal punctuation', () => {
    expect(polishLine('is the moat real?')).toBe('Is the moat real?')
  })

  it('returns empty string for blank input', () => {
    expect(polishLine('   ')).toBe('')
  })
})

describe('polishNotes', () => {
  it('routes "if …" lines to the changers section', () => {
    const { reasons, changers } = polishNotes(BASE.notes)
    expect(reasons).toHaveLength(2)
    expect(changers).toHaveLength(1)
    expect(changers[0]).toMatch(/^If they hire a commercial lead/)
  })

  it('routes Uzbek "agar …" lines to the changers section', () => {
    const { reasons, changers } = polishNotes(BASE_UZ_NOTES)
    expect(reasons).toHaveLength(2)
    expect(changers).toHaveLength(1)
    expect(changers[0]).toMatch(/^Agar tijorat rahbarini yollashsa/)
  })

  it('splits a single multi-sentence line into sentences', () => {
    const { reasons } = polishNotes('rev is strong. team is weak. moat unclear.')
    expect(reasons).toHaveLength(3)
  })
})

describe('composeVerdict', () => {
  it('is deterministic: same input, same letter', () => {
    expect(composeVerdict(BASE)).toBe(composeVerdict(BASE))
  })

  it('produces a structured English letter with polished reasons', () => {
    const letter = composeVerdict(BASE)
    expect(letter).toContain('Dear Otabek Nazarov,')
    expect(letter).toContain('Our decision: we are passing at this time.')
    expect(letter).toContain('Our reasoning:')
    expect(letter).toContain('— Engagement is weak in our view.')
    expect(letter).toContain('— Team is thin with no sales lead.')
    expect(letter).toContain('What would change our answer:')
    expect(letter).toContain('— If they hire a commercial lead id look again.')
    expect(letter).toContain('Laylo Mirzaeva')
    expect(letter).toContain('8 July 2026')
    // Raw shorthand never leaks into the official letter.
    expect(letter).not.toContain('imo')
    expect(letter).not.toContain('w/')
  })

  it('renders the frame in the founder language', () => {
    const uz = composeVerdict({ ...BASE, notes: BASE_UZ_NOTES, lang: 'uz' })
    expect(uz).toContain('Hurmatli Otabek Nazarov,')
    expect(uz).toContain('Sabablarimiz:')
    expect(uz).toContain("Javobimizni nima o'zgartirishi mumkin:")
    expect(uz).toContain("— Agar tijorat rahbarini yollashsa qayta ko'raman.")
    const ru = composeVerdict({ ...BASE, lang: 'ru' })
    expect(ru).toContain('Уважаемый(ая) Otabek Nazarov,')
  })

  it('keeps the Uzbek letter free of the demo note, which lives in en/ru instead', () => {
    const uz = composeVerdict({ ...BASE, notes: BASE_UZ_NOTES, lang: 'uz' })
    expect(uz).not.toContain('Demo')
    const en = composeVerdict({ ...BASE, notes: BASE_UZ_NOTES, lang: 'en' })
    expect(en).toContain('(Demo note:')
    const ru = composeVerdict({ ...BASE, notes: BASE_UZ_NOTES, lang: 'ru' })
    expect(ru).toContain('(Примечание демо:')
  })

  it('adds next steps for advance, and a resubmission path for pass', () => {
    const advance = composeVerdict({ ...BASE, decision: 'advance', notes: 'ready for us intros' })
    expect(advance).toContain('Next steps:')
    const pass = composeVerdict({ ...BASE, notes: 'too early' })
    expect(pass).toContain('What would change our answer:')
  })

  it('reflects edited notes in the recomposed draft', () => {
    const a = composeVerdict(BASE)
    const b = composeVerdict({ ...BASE, notes: BASE.notes + '\nunit economics unproven' })
    expect(b).not.toBe(a)
    expect(b).toContain('— Unit economics unproven.')
  })
})
