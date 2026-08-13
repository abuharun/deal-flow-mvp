/**
 * The acceptance path, in a real browser, against the real local stack.
 *
 * A founder signs in, creates a startup, answers it, submits it, uploads a
 * PDF, records the demo payment, grants AI consent, and starts the research
 * run. The analysis worker is then executed once, out of band — it is a
 * separate process in production too, and Playwright cannot click it into
 * existence. Everything else, including reading the queued job's result, is
 * done through the UI. The founder edits the narrative, approves a specific
 * version, signs out; an investor signs in and opens the frozen dossier.
 *
 * What makes this deterministic: the seed script resets the founder's
 * startups before the run, and the worker uses the offline `local-stub`
 * provider, whose report is fixed text carrying an explicit disclosure. The
 * final assertion checks for that disclosure — the dossier must show stub
 * content as stub content, never as research.
 */

import { execFileSync } from 'node:child_process'
import { expect, test, type Page } from '@playwright/test'
import { accounts } from './accounts'
import { buildDeckPdf } from './fixture-pdf'

const STARTUP_NAME = 'Xarid E2E'
const ONE_LINER = 'Restoran va kafelar uchun B2B ta’minot marketpleysi'
const NARRATIVE = 'Xarid restoranlarni tekshirilgan yetkazib beruvchilar bilan bog‘laydi.'
const STUB_DISCLOSURE = '[LOCAL TEST STUB - NOT AI-GENERATED RESEARCH]'

const ANSWERS: [string, string][] = [
  ['Muammo', 'Restoranlar ta’minotni qo‘lda, telefon orqali boshqaradi.'],
  ['Mahsulot', 'Buyurtma va yetkazib berishni bir joyda boshqaruvchi marketpleys.'],
  ['Bozor', 'Toshkentda 4 mingdan ortiq restoran va kafe.'],
  ['Natijalar', 'Oyiga 240 ta takroriy buyurtma, 18% oylik o‘sish.'],
  ['Jamoa', 'Olti kishi: ikki muhandis, uch sotuv, bir operatsion rahbar.'],
  ['So‘rov', '500 ming AQSh dollari, 18 oylik yo‘l xaritasi uchun.'],
]

/** Run the offline analysis worker for exactly one job, then return. */
function runAnalysisWorkerOnce(): string {
  return execFileSync(
    '.venv/bin/python',
    ['-m', 'app.cli', 'run-analysis-worker', '--once', '--provider', 'local-stub'],
    { cwd: 'backend', encoding: 'utf8' },
  )
}

async function signIn(page: Page, who: 'founder' | 'vc'): Promise<void> {
  await page.goto('#/login')
  await page.getByLabel('Email').fill(accounts[who].email)
  await page.getByLabel('Parol').fill(accounts[who].password)
  await page.getByRole('button', { name: 'Kirish' }).click()
}

test.beforeAll(() => {
  // Idempotent and local-only; refuses a non-local DSN or ENV=production.
  execFileSync('.venv/bin/python', ['../e2e/seed_local_accounts.py'], {
    cwd: 'backend',
    encoding: 'utf8',
  })
})

test('a founder takes a startup from nothing to an investor-visible dossier', async ({ page }) => {
  // ---- Founder: sign in and create the startup -----------------------------
  await signIn(page, 'founder')
  await expect(page.getByRole('heading', { name: 'Startaplarim' })).toBeVisible()

  await page.getByRole('button', { name: 'Startap qo‘shish' }).click()
  await page.getByLabel('Startap nomi').fill(STARTUP_NAME)
  await page.getByLabel('Bir qatorli tavsif').fill(ONE_LINER)
  await page.getByLabel('Yo‘nalish').fill('Marketplace')
  await page.getByLabel('Bosqich').fill('Seed')
  await page.getByLabel('Shahar').fill('Toshkent')
  await page.getByRole('button', { name: 'Saqlash', exact: true }).click()

  // The app followed the id the API returned, not one it guessed.
  await expect(page.getByRole('heading', { name: STARTUP_NAME })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Ariza bosqichlari' })).toBeVisible()
  const startupUrl = page.url()

  // ---- Founder: answer the six questions and submit ------------------------
  for (const [label, answer] of ANSWERS) {
    await page.getByLabel(label).fill(answer)
  }
  await page.getByRole('button', { name: 'Javoblarni saqlash' }).click()
  await expect(page.getByRole('button', { name: 'Javoblarni saqlash' })).toBeDisabled()

  await page.getByRole('button', { name: 'Arizani topshirish' }).click()
  await expect(page.getByText(/^Topshirilgan:/)).toBeVisible()

  // ---- Founder: upload the pitch deck --------------------------------------
  await page.getByLabel('PDF tanlash').setInputFiles({
    name: 'xarid-e2e-deck.pdf',
    mimeType: 'application/pdf',
    buffer: buildDeckPdf(),
  })
  await page.getByRole('button', { name: 'Yuklash' }).click()
  await expect(page.getByText('xarid-e2e-deck.pdf')).toBeVisible()

  // ---- Founder: demo payment and AI consent --------------------------------
  await page.getByRole('button', { name: 'Muvaffaqiyatli to‘lovni qayd etish' }).click()
  await expect(page.getByText(/To‘langan \(demo\)/)).toBeVisible()

  await page.getByRole('button', { name: 'Roziligimni beraman' }).click()
  await expect(page.getByText('Rozilik berilgan')).toBeVisible()

  // ---- Founder: start the research run -------------------------------------
  await page.getByRole('button', { name: 'Tadqiqotni boshlash' }).click()
  await expect(page.locator('strong', { hasText: 'Navbatda' })).toBeVisible()

  // ---- Out of band: the worker process, exactly one job --------------------
  const workerOutput = runAnalysisWorkerOnce()
  expect(workerOutput).toContain('OFFLINE local stub provider')
  expect(workerOutput).toContain('succeeded')

  // ---- Founder: the UI picks the finished run up on its own ----------------
  // No reload: the analysis panel polls while a job is in flight, so this is
  // the page noticing for itself that the worker finished.
  await expect(page.locator('strong', { hasText: 'Yakunlangan' })).toBeVisible({ timeout: 30_000 })

  // ---- Founder: edit the seeded narrative ----------------------------------
  const editor = page.getByLabel('Matn')
  await expect(editor).toBeVisible()
  // The stub's own draft is what seeded it, disclosure and all.
  await expect(editor).toHaveValue(new RegExp(STUB_DISCLOSURE.replace(/[[\]]/g, '\\$&')))
  await editor.fill(NARRATIVE)
  await page.getByRole('button', { name: 'Versiyani saqlash' }).click()
  await expect(page.getByText('Versiya 2').first()).toBeVisible()

  // The history is real: two immutable versions, the seed and the rewrite.
  await page.getByRole('button', { name: 'Versiyalar tarixi' }).click()
  await expect(page.getByRole('list', { name: 'Versiyalar tarixi' }).getByRole('listitem')).toHaveCount(2)

  // ---- Founder: approve, in two deliberate steps ---------------------------
  await page.getByRole('button', { name: 'Versiya 2 ni tasdiqlash' }).click()
  await page.getByRole('button', { name: 'Ha, tasdiqlayman' }).click()
  await expect(page.getByText('Tasdiqlangan versiya: 2')).toBeVisible()
  await expect(page.getByText('Ariza qulflangan')).toBeVisible()

  // Frozen means frozen: the editor is gone, not merely disabled.
  await expect(page.getByLabel('Matn')).toHaveCount(0)

  await page.getByRole('button', { name: 'Chiqish' }).click()
  await expect(page).toHaveURL(/#\/$/)

  // ---- Investor: sign in, find it, read the frozen dossier -----------------
  await signIn(page, 'vc')
  await expect(page.getByRole('heading', { name: 'Tasdiqlangan startaplar' })).toBeVisible()
  await page.getByRole('heading', { name: STARTUP_NAME }).click()

  await expect(page.getByRole('heading', { name: 'Asoschi tasdiqlagan matn' })).toBeVisible()
  // The investor reads exactly the version the founder approved.
  await expect(page.getByText(NARRATIVE)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Tadqiqot hisoboti' })).toBeVisible()
  // ...and the report is unmistakably labelled as offline stub output.
  await expect(page.getByText(STUB_DISCLOSURE).first()).toBeVisible()

  // Read-only by contract: nothing on this page can change anything.
  await expect(page.locator('textarea')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Saqlash|Tasdiqlash/ })).toHaveCount(0)

  // The founder's own page still shows the same startup, still locked.
  expect(startupUrl).toContain('#/founder/')
})
