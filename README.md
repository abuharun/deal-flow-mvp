# Bevosita — deal-flow MVP (frontend demo)

**Bevosita** is an honest deal-flow product connecting startup founders in Uzbekistan
with the standards of US venture capital. A founder submits their startup and pays for a serious
validation; simulated AI standardizes the submission and suggests a priority; a real VC partner
reviews, verifies, decides, and sends a truthful, warmly-worded verdict in the founder's own
language. **The AI drafts; the human is always the author of record.**

**The complete interface is available in Uzbek (Latin script) and Russian.** The language switcher
is available on public, auth, founder, and VC screens; on the landing page it follows the localized
**Baholash / Оценка** assessment link. The choice persists independently in `localStorage`
(`oqim:locale`) and updates the document language, title, and description. The legacy `oqim:*`
storage namespace is intentionally retained so rebranding does not erase existing browser state. Seeded
startup content is also localized dynamically, without duplicating or mutating business state.
Verdict-body language remains a separate choice (Uzbek/Russian/English), and the official English
original of every verdict is preserved as the editable source of truth.

This repository is a **complete, deployable frontend MVP** built from
[`docs/DESIGN_BRIEF.md`](docs/DESIGN_BRIEF.md) and
[`docs/INFORMATION_ARCHITECTURE.md`](docs/INFORMATION_ARCHITECTURE.md). There is no backend: all
data is realistic seeded mock data (canonically stored in Uzbek and displayed in either interface
language), persisted to `localStorage`, so the full
founder → VC → verdict loop is playable end-to-end in one browser.

## Quick start

```bash
npm install
npm run dev        # local dev server
npm test           # vitest (unit + integration)
npm run lint       # eslint
npm run build      # type-check + production build to dist/
npm run preview    # serve the production build
```

Requires Node 20+.

## Demo access

Authentication is simulated — **any password works**. The login page offers a one-click role
chooser; the email decides the role if you use the form:

| Role | Demo identity | Email | Lands on |
|------|---------------|-------|----------|
| Founder (Asoschi) | Dilshod Ergashev | `dilshod@bevosita.demo` (any non-VC email works) | `/apply` — Mening startapim |
| VC partner (Venchur hamkori) | Laylo Mirzaeva | `laylo@bevosita.demo` | `/app` — Pipeline board |

**The full loop, playable:** log in as the founder → submit the six-step form → pay the (stubbed)
validation fee (*baholash to'lovi*) → your startup enters the VC pipeline as *Yangi* (New). Log out,
log in as the VC → open the card → verify, decide, write rough notes → *Xulosa tayyorlash* (Compose
verdict) → edit the draft → *Xulosani yuborish* (Send). Log back in as the founder → the verdict is
waiting, in Uzbek/Russian/English, with a printable official letter.

State is shared through `localStorage`; “Demo ma'lumotlarini qayta o'rnatish” / “Сбросить
демо-данные” (in the founder account or VC settings) restores the seeded pipeline. Interface locale
is stored separately and is not reset with business data.

## Routes

Public: `/` landing · `/login` · `/signup` · `/reset`

Founder (`/apply`, mobile-first, nearly nav-free):
- `/apply` — status home; the copy and primary action change with state (start → continue → under review → decision ready)
- `/apply/submit?step=problem|product|market|traction|team|ask` — six-step submission with autosave (save-and-resume via `localStorage`), per-step validation, focus management, demo attachments
- `/apply/submit/pay` — stubbed validation-fee payment, including a “simulate declined card” path that holds the submission
- `/apply/verdict?lang=uz|ru|en` — the honest verdict in the founder's language, English original always reachable
- `/apply/verdict/letter.pdf` — print-styled official verdict letter (browser print-to-PDF)
- `/apply/account` — profile, billing history, demo reset

VC (`/app`, desktop-first, bottom tabs on mobile):
- `/app` — Kanban pipeline (Yangi / Ko'rib chiqilmoqda / Tavsiya etilgan / AQShga yo'llangan; Rad etilgan collapsed behind a count); signal-sorted columns, per-stage counts; opening a New card moves it to In Review; `?stage=` deep-links a column
- `/app/startups` — the searchable archive: full-text search plus stage / signal / outcome filters and sorting, all URL-synced (`?q=&stage=&signal=&outcome=&sort=`)
- `/app/startups/:id` — deal report: AI summary **beside** raw founder inputs, recommendation framed as guidance, signal re-tagging, verification checklist, decision bar (Tavsiya qilish / Rad etish / AQShga yo'llash), rough notes, verdict composer with inline editing and an explicit two-step **Send**
- `/app/settings` — profile, letter signature and notification stubs, demo reset

## Architecture

React 19 + TypeScript + Vite. No UI framework — a hand-rolled **Calm Blue** design system in
`src/styles.css` (soft blue-white surfaces, dark navy ink, accessible blue brand colors, Fraunces
display + Inter body, and distinct semantic signal colors).

```
src/
  lib/
    types.ts       Domain model — Startup is the one core object everywhere
    seed.ts        11 realistic seeded startups (Uzbek content) across all pipeline stages
    store.tsx      React context + reducer, persisted to localStorage (key oqim:v2)
    compose.ts     Deterministic verdict composer: rough notes → polished letter (en/uz/ru)
    simulate.ts    Deterministic "AI": summary standardization + rule-based recommendation
    verdictText.ts Language resolution for verdict rendering
    content.ts     Pure display overlays for localized seeded/generated content
    seedRu.ts      Russian translations of all seeded startup content
    format.ts      Orderings and deterministic Uzbek/Russian/English date helpers
  i18n/
    index.tsx      Typed locale provider, switch persistence, and document metadata
    uz.tsx         Uzbek source-of-truth dictionary and message schema
    ru.tsx         Russian dictionary, type-checked against the Uzbek schema
  components/      Shells (role chrome + auth guard), signal tag, icons, toast
  pages/           One file per route (founder/, vc/, auth, landing)
  test/            Vitest setup + app-level integration tests
```

Design decisions worth knowing:

- **Deterministic AI stand-ins.** `compose.ts` and `simulate.ts` are pure functions, so the same
  notes always produce the same letter — reproducible demos and testable behavior. Production would
  swap in a real model behind the same contract (notes in, reviewable draft out, nothing auto-sends).
- **Typed localization.** `Messages` is derived from the Uzbek source dictionary; the Russian
  dictionary must satisfy the same shape at compile time. UI locale (`uz|ru`) is deliberately
  separate from verdict language (`uz|ru|en`).
- **Storage schema versioning.** The legacy business-state `localStorage` key remains `oqim:v2` (v2 = Uzbek seed
  content). On first load, `loadState` migrates an existing `oqim:v1` entry by keeping only the
  session, reseeding the content in Uzbek, and removing the old key — deployed users upgrade
  seamlessly instead of seeing stale English data. Current v2 state is preserved while old
  `@oqim.demo` identities and generated Oqim letter branding are migrated to Bevosita display values.
- **Signal is never color alone.** The green/yellow/red system always renders color + distinct icon
  + text label (`SignalTag`), per the accessibility requirement.
- **Honest stubs.** Every simulated boundary (payment, uploads, translations, notifications) is
  visibly labeled in the UI rather than faked silently.
- **Accessibility**: semantic landmarks, localized labeled controls, visible focus states, skip
  links, focus management on form-step changes, `aria-live` for autosave/counts, reduced-motion
  support, WCAG-AA-checked palette. The document `lang` follows the interface locale; verdict
  letters set `lang` independently per selected body language.

## Tests

`npm test` runs Vitest (jsdom + Testing Library):

- `compose.test.ts` — shorthand polishing, "if …" / "agar …" routing to *what would change our
  answer*, letter structure per decision/language, determinism
- `simulate.test.ts` — summarization and recommendation rules (Uzbek and English keywords)
- `store.test.ts` — reducer: payment gate, verification, compose→edit→send stage moves, reset,
  persistence, and the v1 → v2 storage migration
- `ui.test.tsx` — signal tag renders label + icon + color, never color alone
- `app.test.tsx` — integration: routing guards, demo login, founder submission autosave, locale
  switching and persistence, Russian settings/archive/detail/seeded content, and the full VC review
  → compose → edit → send loop
- `i18n/localization.test.ts` — deterministic Russian dates, complete seeded-content overlays,
  canonical-state immutability, and verdict-body language independence
- `styles.test.ts` — deterministic WCAG contrast checks for key text, button, and signal color pairs

## Deployment (GitHub Pages)

- `vite.config.ts` sets `base: '/deal-flow-mvp/'` to match the project-pages URL.
- Routing uses **HashRouter**, so deep links (e.g. `…/deal-flow-mvp/#/app/startups/st_…`) work on
  Pages without server rewrites.
- Deployment is manual, from a `gh-pages` branch (no GitHub Actions required):

  ```bash
  npm run build                      # produces dist/
  git checkout --orphan gh-pages     # or: git checkout gh-pages, if it exists
  git rm -rf .                       # clear the branch's working tree
  cp -r dist/* .                     # copy the build output to the branch root
  git add -A && git commit -m "deploy"
  git push origin gh-pages
  git checkout main
  ```

  Then enable **Settings → Pages → Source: Deploy from a branch → `gh-pages` / root** in the
  repo once. Re-run the steps above to publish updates.

## Deployment (Render pilot)

[`render.yaml`](render.yaml) is a Render Blueprint that stands up the full stack for a paid pilot:
managed Postgres, the FastAPI API, the AI analysis background worker, and the static frontend —
all on the smallest paid plans, roughly **$20/month** (Postgres `basic-256mb` ~$6 + API `starter`
~$7 + worker `starter` ~$7; the static site is always free on Render), leaving headroom under a
~$25/month budget.

**Deploy:** Render dashboard → **New → Blueprint** → point at this repo/branch → apply. This
creates `bevosita-db`, `bevosita-api`, `bevosita-analysis-worker`, and `bevosita-app`.

**What's wired up already:**
- Health checks: the API's `healthCheckPath` is `/readyz` (DB reachable *and* migrations at head),
  so Render won't cut a new deploy over until the database is actually ready; `/healthz` stays a
  pure liveness check.
- Migrations: `preDeployCommand` runs `python -m app.cli migrate` (`backend/app/cli.py`) before
  every new API release goes live — an `alembic upgrade head` wrapper with a safe, DSN-free error
  message on failure.
- `DATABASE_URL` scheme: Render's Postgres connection string is `postgresql://…`, but
  `Settings` requires the `postgresql+asyncpg://` driver prefix in production. Every service's
  start/pre-deploy command rewrites the scheme in-shell before Python starts — no app code needs to
  know about Render's URL shape.
- CORS / public URLs: `FRONTEND_ORIGINS`, `API_PUBLIC_URL`, and `FRONTEND_PUBLIC_URL` are
  pre-filled from the blueprint's own service names (`https://bevosita-api.onrender.com` /
  `https://bevosita-app.onrender.com`). **If either name is already taken**, Render suffixes the
  hostname and you must update these three values (plus the frontend's `VITE_API_BASE_URL`) by hand
  after the first deploy — Blueprints can't cross-reference another service's public URL.
- Static frontend routing: the frontend build sets `VITE_BASE_PATH=/` (see `vite.config.ts`, which
  otherwise defaults to `/deal-flow-mvp/` for GitHub Pages) and a catch-all rewrite to
  `index.html`. Routing is HashRouter, so this rewrite is defense-in-depth, not strictly required.
- `JWT_SECRET` is a Render `generateValue` secret (independently generated for the API and the
  worker — the worker never issues or verifies a JWT, so the two never need to match).

**You must supply before the stack is fully functional** (Render prompts for these at blueprint
creation, or set them later in the dashboard — never commit them):
- `OPENAI_API_KEY` on `bevosita-analysis-worker` (and pricing already defaults to `gpt-4o-mini`
  rates) — without it the worker starts, refuses to process jobs, and exits/restarts
  (`require_worker_config` in `backend/app/services/analysis_worker_config.py`); the API and
  frontend still work, founder submissions just queue with no analysis produced.
- `RESEND_API_KEY` and a verified `EMAIL_FROM` — only if you switch `EMAIL_MODE` from its pilot
  default of `console` to `resend_prod`. The pilot ships with founder/VC accounts provisioned via
  `python -m app.cli create-invite` / `create-vc-owner` (prints the activation URL directly), so no
  outbound email is required to onboard pilot users.
- `SENTRY_DSN`, `BACKUP_BUCKET_URL`, `BACKUP_AGE_PUBLIC_KEY` — reserved keys for future
  observability/backup wiring; not read by the app yet, safe to leave unset.

**Known limitation:** `TRUSTED_PROXY_CIDRS` is left empty because Render's edge-proxy IP range
isn't a published, stable CIDR — trusting a guessed range would let `X-Forwarded-For` be spoofed
(see `backend/app/security/client_ip.py`). Effect: the per-IP rate limiter currently buckets by
Render's proxy peer address rather than the real visitor's IP. Fine for a pilot; revisit if
precise per-user rate limiting becomes a launch requirement.

## Limitations (deliberate, frontend-only)

- No backend: auth, data, and "notifications" live in `localStorage`; two browsers don't share state.
- Payment is a stub — no gateway is called, no card data leaves the page.
- File uploads are simulated (names only); attachments aren't downloadable.
- The verdict letter "PDF" uses the browser's print-to-PDF.
- Verdict translations are deterministic templates: the letter frame is genuinely localized
  (uz/ru/en), while notes-derived reasons stay in the language of the partner's notes (Uzbek in the
  demo), with a visible demo note in the English and Russian letters.
- Out of scope per the brief: real AI quality, multi-VC tenancy, CRM depth.
