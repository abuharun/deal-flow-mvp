/**
 * The founder's real write path, driven through the real router.
 *
 * Every test below clicks something a founder can actually click and asserts
 * on the HTTP call that reached the fake backend — the endpoint, the method,
 * and the exact body. Nothing here asserts on component internals, so the
 * suite fails if the UI stops talking to the documented contract, not if the
 * markup is rearranged.
 */

import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  apiCalls,
  bodyOf,
  envelope,
  grantSession,
  installFakeApi,
  json,
  renderApp,
  route,
} from '../../test/harness'
import {
  makeAnalysisJob,
  makeApproval,
  makeConsents,
  makeDeck,
  makeNarrative,
  makePayment,
  makeStartup,
  makeStartupDetail,
} from '../../test/factories'
import type { StartupResponse } from '../../api/types'
import { ANALYSIS_POLL_INTERVAL_MS } from './AnalysisPanel'

const NOT_FOUND = {
  deck: () => envelope('DECK_NOT_FOUND', 404),
  payment: () => envelope('PAYMENT_NOT_FOUND', 404),
  analysis: () => envelope('ANALYSIS_NOT_FOUND', 404),
  narrative: () => envelope('NARRATIVE_NOT_READY', 409),
  approval: () => envelope('NARRATIVE_NOT_APPROVED', 404),
}

/** The seven reads the detail page makes; each is overridable per test. */
function detailRoutes(
  overrides: Partial<Record<'startup' | 'deck' | 'payment' | 'consents' | 'analysis' | 'narrative' | 'approval', () => Response>> = {},
) {
  const id = 'startup-1'
  route(`GET /founder/startups/${id}`, overrides.startup ?? (() => json(makeStartupDetail())))
  route(`GET /founder/startups/${id}/deck/metadata`, overrides.deck ?? NOT_FOUND.deck)
  route(`GET /founder/startups/${id}/payment`, overrides.payment ?? NOT_FOUND.payment)
  route(`GET /founder/startups/${id}/consents`, overrides.consents ?? (() => json(makeConsents({ granted: false, history: [] }))))
  route(`GET /founder/startups/${id}/analysis`, overrides.analysis ?? NOT_FOUND.analysis)
  route(`GET /founder/startups/${id}/narrative`, overrides.narrative ?? NOT_FOUND.narrative)
  route(`GET /founder/startups/${id}/narrative/approval`, overrides.approval ?? NOT_FOUND.approval)
}

/** A startup whose earlier steps are all done, so one panel can be tested alone. */
function readyDetail(overrides: Partial<StartupResponse> = {}) {
  return makeStartupDetail({
    status: 'report_ready',
    submitted_at: '2026-07-21T09:00:00Z',
    submission: {
      problem: 'Restoranlar',
      product: 'Marketpleys',
      market: 'B2B',
      traction: '240',
      team: '6',
      ask: '$500k',
    },
    ...overrides,
  })
}

beforeEach(() => {
  localStorage.clear()
  installFakeApi()
  grantSession('founder')
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('creating a startup', () => {
  it('posts the founder’s own metadata and opens the new startup', async () => {
    const user = userEvent.setup()
    route('GET /founder/startups', () => json([]))
    route('POST /founder/startups', () => json(makeStartupDetail({ id: 'startup-1', name: 'Xarid' }), 201))
    detailRoutes()

    renderApp('/founder')
    await user.click(await screen.findByRole('button', { name: 'Startap qo‘shish' }))

    await user.type(screen.getByLabelText('Startap nomi'), 'Xarid')
    await user.type(screen.getByLabelText('Yo‘nalish'), 'Marketplace')
    await user.click(screen.getByRole('button', { name: 'Saqlash' }))

    expect(bodyOf('POST /founder/startups')).toEqual({
      name: 'Xarid',
      one_liner: '',
      sector: 'Marketplace',
      funding_stage: '',
      city: '',
    })
    // The app lands on the startup the API returned, not on a guessed id.
    expect(await screen.findByRole('list', { name: 'Ariza bosqichlari' })).toBeInTheDocument()
  })

  it('keeps the founder on the form and shows the API’s reason when creation fails', async () => {
    const user = userEvent.setup()
    route('GET /founder/startups', () => json([]))
    route('POST /founder/startups', () => envelope('VALIDATION_FAILED', 422))

    renderApp('/founder')
    await user.click(await screen.findByRole('button', { name: 'Startap qo‘shish' }))
    await user.type(screen.getByLabelText('Startap nomi'), 'Xarid')
    await user.click(screen.getByRole('button', { name: 'Saqlash' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Kiritilgan ma’lumotlar to‘g‘ri emas.')
    expect(screen.getByLabelText('Startap nomi')).toHaveValue('Xarid')
  })

  it('never posts a blank name', async () => {
    const user = userEvent.setup()
    route('GET /founder/startups', () => json([]))

    renderApp('/founder')
    await user.click(await screen.findByRole('button', { name: 'Startap qo‘shish' }))
    await user.click(screen.getByRole('button', { name: 'Saqlash' }))

    expect(apiCalls()).not.toContain('POST /founder/startups')
  })
})

describe('editing startup metadata', () => {
  it('patches only the fields the founder changed', async () => {
    const user = userEvent.setup()
    detailRoutes({ startup: () => json(makeStartupDetail({ city: 'Toshkent' })) })
    route('PATCH /founder/startups/startup-1', () => json(makeStartup({ city: 'Samarqand' })))

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Tahrirlash' }))

    const city = screen.getByLabelText('Shahar')
    await user.clear(city)
    await user.type(city, 'Samarqand')
    await user.click(screen.getByRole('button', { name: 'Saqlash' }))

    await waitFor(() => expect(apiCalls()).toContain('PATCH /founder/startups/startup-1'))
    expect(bodyOf('PATCH /founder/startups/startup-1')).toEqual({ city: 'Samarqand' })
  })

  it('offers no edit control once the startup is frozen', async () => {
    detailRoutes({
      startup: () => json(readyDetail({ status: 'vc_visible', vc_visible_at: '2026-07-25T09:00:00Z' })),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => json(makeAnalysisJob({ status: 'completed' })),
      narrative: () => json(makeNarrative()),
      approval: () => json(makeApproval()),
    })

    renderApp('/founder/startup-1')

    expect(await screen.findByText('Ariza qulflangan')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Tahrirlash' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Tasdiqlash/ })).not.toBeInTheDocument()
  })
})

describe('the progress summary above the rail', () => {
  it('counts only the steps the API actually reports as done', async () => {
    detailRoutes({ startup: () => json(readyDetail()) })

    renderApp('/founder/startup-1')

    // Only the submission is done at this point (deck/payment/consent/analysis/narrative/approval are not).
    expect(await screen.findByText('1/7 bosqich bajarildi')).toBeInTheDocument()
  })

  it('advances as each prerequisite becomes done', async () => {
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => json(makeAnalysisJob({ status: 'completed' })),
      narrative: () => json(makeNarrative()),
    })

    renderApp('/founder/startup-1')

    expect(await screen.findByText('6/7 bosqich bajarildi')).toBeInTheDocument()
  })
})

describe('answering the submission and submitting it', () => {
  it('saves only the answers that actually changed', async () => {
    const user = userEvent.setup()
    detailRoutes()
    route('PATCH /founder/startups/startup-1/submission', () => json(makeStartupDetail()))

    renderApp('/founder/startup-1')
    await user.type(await screen.findByLabelText('Muammo'), 'Restoranlar ta’minotni qo‘lda boshqaradi')
    await user.click(screen.getByRole('button', { name: 'Javoblarni saqlash' }))

    await waitFor(() => expect(apiCalls()).toContain('PATCH /founder/startups/startup-1/submission'))
    expect(bodyOf('PATCH /founder/startups/startup-1/submission')).toEqual({
      problem: 'Restoranlar ta’minotni qo‘lda boshqaradi',
    })
  })

  it('submits the application and reports the API’s missing-answer list', async () => {
    const user = userEvent.setup()
    detailRoutes({ startup: () => json(readyDetail({ status: 'draft', submitted_at: null })) })
    route('POST /founder/startups/startup-1/submit', () => envelope('SUBMISSION_INCOMPLETE', 422))

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Arizani topshirish' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Barcha savollarga javob berilmagan.')
  })

  it('reloads the startup after a successful submit', async () => {
    const user = userEvent.setup()
    let submitted = false
    detailRoutes({
      startup: () =>
        json(readyDetail({ status: submitted ? 'submitted' : 'draft', submitted_at: submitted ? '2026-07-21T09:00:00Z' : null })),
    })
    route('POST /founder/startups/startup-1/submit', () => {
      submitted = true
      return json(makeStartup({ status: 'submitted', submitted_at: '2026-07-21T09:00:00Z' }))
    })

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Arizani topshirish' }))

    expect(await screen.findByText(/Topshirilgan:/)).toBeInTheDocument()
  })
})

describe('uploading the pitch deck', () => {
  it('PUTs the chosen PDF as multipart and shows what the API stored', async () => {
    const user = userEvent.setup()
    let uploaded = false
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => (uploaded ? json(makeDeck({ filename: 'xarid-deck.pdf' })) : NOT_FOUND.deck()),
    })
    route('PUT /founder/startups/startup-1/deck', () => {
      uploaded = true
      return json(makeDeck({ filename: 'xarid-deck.pdf' }), 201)
    })

    renderApp('/founder/startup-1')
    const file = new File(['%PDF-1.4 stub'], 'xarid-deck.pdf', { type: 'application/pdf' })
    await user.upload(await screen.findByLabelText('PDF tanlash'), file)
    await user.click(screen.getByRole('button', { name: 'Yuklash' }))

    await waitFor(() => expect(apiCalls()).toContain('PUT /founder/startups/startup-1/deck'))
    const body = bodyOf('PUT /founder/startups/startup-1/deck') as FormData
    expect((body.get('file') as File).name).toBe('xarid-deck.pdf')
    expect(await screen.findByText('xarid-deck.pdf')).toBeInTheDocument()
  })

  it('shows the API’s refusal for a file that is not really a PDF', async () => {
    const user = userEvent.setup()
    detailRoutes({ startup: () => json(readyDetail()) })
    route('PUT /founder/startups/startup-1/deck', () => envelope('DECK_INVALID_PDF', 422))

    renderApp('/founder/startup-1')
    await user.upload(
      await screen.findByLabelText('PDF tanlash'),
      new File(['not really a pdf'], 'notes.pdf', { type: 'application/pdf' }),
    )
    await user.click(screen.getByRole('button', { name: 'Yuklash' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Fayl yaroqli PDF emas.')
  })

  it('never uploads before a file has been chosen', async () => {
    detailRoutes({ startup: () => json(readyDetail()) })

    renderApp('/founder/startup-1')
    await screen.findByLabelText('PDF tanlash')

    expect(screen.queryByRole('button', { name: 'Yuklash' })).not.toBeInTheDocument()
  })
})

describe('the demo payment and the AI consent', () => {
  it('records the outcome the founder explicitly chose', async () => {
    const user = userEvent.setup()
    let paid = false
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => (paid ? json(makePayment()) : NOT_FOUND.payment()),
    })
    route('POST /founder/startups/startup-1/payment', () => {
      paid = true
      return json(makePayment(), 201)
    })

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Muvaffaqiyatli to‘lovni qayd etish' }))

    await waitFor(() => expect(apiCalls()).toContain('POST /founder/startups/startup-1/payment'))
    expect(bodyOf('POST /founder/startups/startup-1/payment')).toEqual({ simulate_outcome: 'paid' })
    expect(await screen.findByText(/To‘langan \(demo\)/)).toBeInTheDocument()
  })

  it('offers the declined-card path too, exactly as the demo contract allows', async () => {
    const user = userEvent.setup()
    detailRoutes({ startup: () => json(readyDetail()), deck: () => json(makeDeck()) })
    route('POST /founder/startups/startup-1/payment', () => json(makePayment({ status: 'failed', paid_at: null }), 201))

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Muvaffaqiyatsiz to‘lovni qayd etish' }))

    await waitFor(() => expect(apiCalls()).toContain('POST /founder/startups/startup-1/payment'))
    expect(bodyOf('POST /founder/startups/startup-1/payment')).toEqual({ simulate_outcome: 'failed' })
  })

  it('keeps the payment and consent controls secondary while an earlier step is still open', async () => {
    detailRoutes({ startup: () => json(readyDetail()) })

    renderApp('/founder/startup-1')

    const pay = await screen.findByRole('button', { name: 'Muvaffaqiyatli to‘lovni qayd etish' })
    expect(pay).toHaveClass('btn-secondary')
    expect(pay).not.toHaveClass('btn-primary')
    const grant = screen.getByRole('button', { name: 'Roziligimni beraman' })
    expect(grant).toHaveClass('btn-secondary')
    expect(grant).not.toHaveClass('btn-primary')
  })

  it('promotes the payment control to primary once the deck is uploaded, while consent stays secondary', async () => {
    detailRoutes({ startup: () => json(readyDetail()), deck: () => json(makeDeck()) })

    renderApp('/founder/startup-1')

    const pay = await screen.findByRole('button', { name: 'Muvaffaqiyatli to‘lovni qayd etish' })
    expect(pay).toHaveClass('btn-primary')
    const grant = screen.getByRole('button', { name: 'Roziligimni beraman' })
    expect(grant).toHaveClass('btn-secondary')
  })

  it('promotes the consent control to primary once payment is recorded', async () => {
    detailRoutes({ startup: () => json(readyDetail()), deck: () => json(makeDeck()), payment: () => json(makePayment()) })

    renderApp('/founder/startup-1')

    const grant = await screen.findByRole('button', { name: 'Roziligimni beraman' })
    expect(grant).toHaveClass('btn-primary')
  })

  it('grants consent at the exact version the server is currently asking for', async () => {
    const user = userEvent.setup()
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents({ current_version: 'ai-privacy.v3', granted: false, history: [] })),
    })
    route('POST /founder/startups/startup-1/consents', () => json({ id: 'c1', kind: 'ai_privacy', text_version: 'ai-privacy.v3', granted_at: '2026-07-22T09:00:00Z' }, 201))

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Roziligimni beraman' }))

    await waitFor(() => expect(apiCalls()).toContain('POST /founder/startups/startup-1/consents'))
    expect(bodyOf('POST /founder/startups/startup-1/consents')).toEqual({
      kind: 'ai_privacy',
      text_version: 'ai-privacy.v3',
    })
  })
})

describe('triggering and following the AI analysis', () => {
  function allPrerequisitesMet() {
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
    })
  }

  it('triggers the run and shows the job the API queued', async () => {
    const user = userEvent.setup()
    let queued = false
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => (queued ? json(makeAnalysisJob({ status: 'queued' })) : NOT_FOUND.analysis()),
    })
    route('POST /founder/startups/startup-1/analysis', () => {
      queued = true
      return json(makeAnalysisJob({ status: 'queued' }), 202)
    })

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Tadqiqotni boshlash' }))

    await waitFor(() => expect(apiCalls()).toContain('POST /founder/startups/startup-1/analysis'))
    expect(await screen.findByText('Navbatda', { selector: 'strong' })).toBeInTheDocument()
  })

  it('lists the missing prerequisites instead of offering a trigger that must fail', async () => {
    detailRoutes({ startup: () => json(readyDetail()) })

    renderApp('/founder/startup-1')

    expect(await screen.findByText('Tadqiqot uchun quyidagilar kerak:')).toBeInTheDocument()
    expect(screen.getByText('Taqdimot yuklanmagan')).toBeInTheDocument()
    expect(screen.getByText('Demo to‘lov qayd etilmagan')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Tadqiqotni boshlash' })).not.toBeInTheDocument()
  })

  it('polls a running job and stops once the API reports a terminal state', async () => {
    vi.useFakeTimers()
    let polls = 0
    let narrativeReady = false
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => {
        polls += 1
        return json(makeAnalysisJob({ status: polls >= 2 ? 'completed' : 'running' }))
      },
      narrative: () => (narrativeReady ? json(makeNarrative()) : NOT_FOUND.narrative()),
    })

    renderApp('/founder/startup-1')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.getByText('Bajarilmoqda', { selector: 'strong' })).toBeInTheDocument()

    narrativeReady = true
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_INTERVAL_MS)
    })
    expect(screen.getByText('Yakunlangan', { selector: 'strong' })).toBeInTheDocument()

    // Terminal means terminal: no further polling once it completed.
    const settled = polls
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ANALYSIS_POLL_INTERVAL_MS * 3)
    })
    expect(polls).toBe(settled)
  })

  it('does not offer a second trigger once a job exists', async () => {
    allPrerequisitesMet()
    route('GET /founder/startups/startup-1/analysis', () => json(makeAnalysisJob({ status: 'completed' })))

    renderApp('/founder/startup-1')
    await screen.findByText('Yakunlangan', { selector: 'strong' })

    expect(screen.queryByRole('button', { name: 'Tadqiqotni boshlash' })).not.toBeInTheDocument()
  })
})

describe('the narrative and its version history', () => {
  function withNarrative(extra: Parameters<typeof detailRoutes>[0] = {}) {
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => json(makeAnalysisJob({ status: 'completed' })),
      narrative: () => json(makeNarrative({ version: 1, content: 'Seeded draft.' })),
      ...extra,
    })
  }

  it('saves the founder’s rewrite as a new version', async () => {
    const user = userEvent.setup()
    withNarrative()
    route('PATCH /founder/startups/startup-1/narrative', () =>
      json(makeNarrative({ version: 2, source: 'founder_edit', content: 'Bizning matnimiz.' })),
    )

    renderApp('/founder/startup-1')
    const editor = await screen.findByLabelText('Matn')
    await user.clear(editor)
    await user.type(editor, 'Bizning matnimiz.')
    await user.click(screen.getByRole('button', { name: 'Versiyani saqlash' }))

    await waitFor(() => expect(apiCalls()).toContain('PATCH /founder/startups/startup-1/narrative'))
    expect(bodyOf('PATCH /founder/startups/startup-1/narrative')).toEqual({ content: 'Bizning matnimiz.' })
  })

  it('never saves an empty narrative', async () => {
    const user = userEvent.setup()
    withNarrative()

    renderApp('/founder/startup-1')
    await user.clear(await screen.findByLabelText('Matn'))
    await user.click(screen.getByRole('button', { name: 'Versiyani saqlash' }))

    expect(apiCalls()).not.toContain('PATCH /founder/startups/startup-1/narrative')
  })

  it('loads the history only when the founder opens it, then shows one version’s text', async () => {
    const user = userEvent.setup()
    withNarrative()
    route('GET /founder/startups/startup-1/narrative/versions', () =>
      json({
        current_version: 2,
        versions: [
          { version: 1, source: 'report_seed', report_id: 'r1', input_revision: 1, content_length: 13, created_at: '2026-07-22T09:00:00Z' },
          { version: 2, source: 'founder_edit', report_id: 'r1', input_revision: 1, content_length: 17, created_at: '2026-07-23T09:00:00Z' },
        ],
      }),
    )
    route('GET /founder/startups/startup-1/narrative/versions/1', () =>
      json({ version: 1, content: 'Seeded draft.', source: 'report_seed', report_id: 'r1', input_revision: 1, created_at: '2026-07-22T09:00:00Z' }),
    )

    renderApp('/founder/startup-1')
    await screen.findByLabelText('Matn')
    expect(apiCalls()).not.toContain('GET /founder/startups/startup-1/narrative/versions')

    await user.click(screen.getByRole('button', { name: 'Versiyalar tarixi' }))
    const history = await screen.findByRole('list', { name: 'Versiyalar tarixi' })
    expect(within(history).getAllByRole('listitem')).toHaveLength(2)

    await user.click(within(history).getAllByRole('button', { name: 'Ko‘rish' })[0])
    // The frozen text of version 1, rendered as read-only prose beside the
    // editor that still holds the current draft.
    const preview = await screen.findByText('Seeded draft.', { selector: '.narrative-text' })
    expect(preview).toBeInTheDocument()
    expect(apiCalls()).toContain('GET /founder/startups/startup-1/narrative/versions/1')
  })
})

describe('approving and sending to investors', () => {
  function readyToApprove() {
    detailRoutes({
      startup: () => json(readyDetail()),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => json(makeAnalysisJob({ status: 'completed' })),
      narrative: () => json(makeNarrative({ version: 2, source: 'founder_edit' })),
    })
  }

  it('requires an explicit confirmation before freezing anything', async () => {
    const user = userEvent.setup()
    readyToApprove()
    route('POST /founder/startups/startup-1/narrative/approval', () => json(makeApproval({ version: 2 })))

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Versiya 2 ni tasdiqlash' }))

    // One click only arms the confirmation; nothing has been sent yet.
    expect(apiCalls()).not.toContain('POST /founder/startups/startup-1/narrative/approval')

    await user.click(screen.getByRole('button', { name: 'Ha, tasdiqlayman' }))
    await waitFor(() => expect(apiCalls()).toContain('POST /founder/startups/startup-1/narrative/approval'))
    // The version the founder was looking at, never "whatever is current".
    expect(bodyOf('POST /founder/startups/startup-1/narrative/approval')).toEqual({ version: 2 })
  })

  it('lets the founder back out of the confirmation', async () => {
    const user = userEvent.setup()
    readyToApprove()

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Versiya 2 ni tasdiqlash' }))
    await user.click(screen.getByRole('button', { name: 'Bekor qilish' }))

    expect(apiCalls()).not.toContain('POST /founder/startups/startup-1/narrative/approval')
    expect(screen.getByRole('button', { name: 'Versiya 2 ni tasdiqlash' })).toBeInTheDocument()
  })

  it('surfaces a version race as the API’s own conflict, not a silent overwrite', async () => {
    const user = userEvent.setup()
    readyToApprove()
    route('POST /founder/startups/startup-1/narrative/approval', () => envelope('NARRATIVE_VERSION_MISMATCH', 409))

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Versiya 2 ni tasdiqlash' }))
    await user.click(screen.getByRole('button', { name: 'Ha, tasdiqlayman' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Sahifani yangilab, qayta tasdiqlang/)
  })

  it('shows the frozen result once the API has approved it', async () => {
    const user = userEvent.setup()
    let approved = false
    detailRoutes({
      startup: () => json(readyDetail(approved ? { status: 'vc_visible', vc_visible_at: '2026-07-25T09:00:00Z' } : {})),
      deck: () => json(makeDeck()),
      payment: () => json(makePayment()),
      consents: () => json(makeConsents()),
      analysis: () => json(makeAnalysisJob({ status: 'completed' })),
      narrative: () => json(makeNarrative({ version: 2, source: 'founder_edit' })),
      approval: () => (approved ? json(makeApproval({ version: 2 })) : NOT_FOUND.approval()),
    })
    route('POST /founder/startups/startup-1/narrative/approval', () => {
      approved = true
      return json(makeApproval({ version: 2 }))
    })

    renderApp('/founder/startup-1')
    await user.click(await screen.findByRole('button', { name: 'Versiya 2 ni tasdiqlash' }))
    await user.click(screen.getByRole('button', { name: 'Ha, tasdiqlayman' }))

    expect(await screen.findByText('Tasdiqlangan versiya: 2')).toBeInTheDocument()
    expect(await screen.findByText('Ariza qulflangan')).toBeInTheDocument()
  })
})
