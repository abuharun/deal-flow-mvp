# Design Brief: Deal-Flow MVP — End-to-End Screening Loop

*Greenfield. No existing codebase or design system. This brief establishes the starting vocabulary; the design-tokens skill runs next.*

*Scope chosen: the thinnest complete loop — founder submits → AI summarizes & recommends → VC screens a sorted queue → VC decides & replies. Built as the daily tool for one insider VC partner in one country (Uzbekistan), per the project strategy brief.*

## Problem

Two people are stuck at opposite ends of the same broken pipe.

A founder in Tashkent has a company and no idea whether it's fundable by global standards. The path to US capital is opaque, bureaucratic, and gated by networks they don't have. They can't tell if their idea is a real venture or a local business, and no one will tell them the truth.

A VC partner receives a stream of inbound founders and has no fast, trustworthy way to sort them. Reading every raw submission cold is slow; ignoring them means missing the few that matter. Today this triage is manual, inconsistent, and lives in their head and inbox.

Neither person needs more startups or more capital in the abstract. The founder needs an honest verdict and a path. The VC needs *signal* — the few worth their attention — without doing all the reading themselves.

## Solution

One connected loop with a human always in the seat of judgment.

A founder submits their startup through a structured flow and pays for an honest validation. The system produces a standardized summary and a readiness recommendation — not to decide, but to make the founder legible fast. That lands in the VC partner's queue, sorted green/yellow/red purely to rank attention. The partner opens a deal, reviews the summary against the founder's raw inputs, ticks off a light verification pass, and makes the call — recommend, pass, or advance toward a US intro. The partner writes their reasoning in rough — a few blunt notes, grammar and structure be damned — and the AI turns it into a clean, official, correctly-structured verdict in the founder's own language, with the English original preserved. The partner reviews and edits that document before it ever sends; the AI never speaks to the founder unsupervised. The founder receives a real, respectful verdict with a reason — polished enough to feel official, honest enough to be useful.

The AI is the labor-saver. The human is the trust layer. The interface's whole job is to make that division visible and keep the person in control.

## Experience Principles

1. **Trust over automation** — The AI drafts summaries and suggests a color, but the interface always shows *whose claim* is *whose*, keeps the human's verification and override one action away, and never hides raw founder input behind a generated summary. Speed must never cost credibility.
2. **Honest over flattering** — Founders receive truthful verdicts, delivered warmly but without softening the substance. The product's value *is* the truth; the design should make hard feedback feel respectful, not discouraging.
3. **Prioritize, never pronounce** — Color and recommendations rank attention; they are never presented as a verdict. The VC decides after real review. The UI must visibly frame every AI output as a starting point, not an answer.

## Aesthetic Direction

- **Philosophy**: **Warm Clarity** — humane, trustworthy, and calm. Warmth without sacrificing the seriousness capital demands. Approachable enough that a nervous first-time founder isn't intimidated, credible enough that a VC trusts it with daily work.
- **Tone**: Warm, honest, confidence-inspiring, unhurried. Not clinical, not a cold data terminal, not hypey or gamified.
- **Reference points**: Notion (warm clarity, generous space), Mercury (serious-but-human fintech), Linear/Attio (clean structure for the queue, softened), Stripe (plainspoken clarity in dense content).
- **Anti-references**: Bloomberg terminal (too cold and dense), "Tinder-for-startups" gamified pitch apps, generic blue-and-white enterprise CRM, hypey web3 gradients.

## Existing Patterns

None — greenfield. No tokens, components, fonts, or framework in place. This is a note, not a constraint: the next step (design-tokens) sets the palette, type ramp, and spacing scale from the Warm Clarity philosophy above. Two aesthetic anchors to carry into that work: color is reserved for *signal and warmth*, not decoration; and numerics (revenue, traction, dates) should be visually distinct and scannable.

## Component Inventory

Everything is New (greenfield). Status column kept for continuity with later skills.

| Component | Status | Notes |
| --------- | ------ | ----- |
| Auth + role routing (founder / VC) | New | Two roles, one codebase. Minimal for pilot. |
| Multi-step submission form | New | Problem, product, market, traction, team, ask. Save-and-resume. Mobile-first. |
| File / link upload | New | Pitch deck, data-room link, revenue proof. |
| Validation payment step | New | Stub for pilot (Stripe later). Gate before submission completes. |
| AI processing / pending state | New | Async "we're reviewing" state for the founder. |
| AI summary card | New | Standardized structured summary of the founder's inputs. |
| Readiness / recommendation card | New | The recommendation, clearly framed as guidance not verdict. |
| Deal queue (sortable list) | New | VC's daily workspace. Sort/filter by color, stage, date. Desktop-first. |
| Color signal tag | New | Green/yellow/red — always paired with a text label + icon, never color alone. |
| Deal report / detail view | New | Summary + recommendation + raw founder inputs side by side. |
| Verification checklist | New | Light human proof-check: revenue, cap table, references. |
| Decision action bar | New | Recommend / Pass / Advance-to-US, plus a rough-notes reason field. |
| Verdict composer (AI polish) | New | Turns the VC's rough notes into a structured, grammatically-clean, official verdict. VC reviews and edits before send; AI never sends unsupervised. |
| Language / translation toggle | New | Verdict rendered in the founder's language with the English original preserved. |
| PDF verdict letter | New | Downloadable official letter (branded, dated, signed-off), generated from the approved verdict. |
| Founder verdict / response view | New | The honest reply the founder receives — formatted in-app in their language, with a PDF letter to download. |
| Empty & loading states | New | Warm, guiding — especially the founder's waiting state. |

## Key Interactions

**Founder submission.** Multi-step form with visible progress and save-and-resume; a founder on a phone with a spotty connection must not lose work. Payment gates completion; on submit, the founder lands on a warm pending state that sets honest expectations about timing.

**AI processing.** Submission triggers async generation of the summary and recommendation. The founder sees a calm "under review" state, not a spinner that implies instant judgment.

**VC triage.** The partner opens the queue, sorted by color, and can filter by stage/date. Clicking a row opens the deal report. The color is display-only signal; the partner can re-tag it. Keyboard navigation through the queue is desirable but not required for the pilot.

**VC review & decision.** In the report, the AI summary sits *beside* the founder's raw inputs so nothing is hidden behind generation. The partner ticks verification items, picks an action, and writes their reasoning in *rough* — the point is to let them think in blunt shorthand, not to compose prose. On request, the **verdict composer** turns those notes into a structured, grammatically-clean, official verdict in the founder's language (English original kept alongside). The partner then reviews and edits the polished draft in place, and only their explicit **Send** dispatches it — the AI never speaks to the founder unsupervised. Editing the notes and re-polishing is cheap; the composer is a draft assistant, not the author of record.

**Founder receives verdict.** An honest, warmly-worded, official-feeling response in the founder's own language — clear decision, the reason, and where relevant what would change the answer — readable in-app and downloadable as a branded PDF letter.

## Responsive Behavior

Two audiences, two default devices — this is a genuine behavior split, not just resizing.

- **Founder side: mobile-first.** Uzbek founders will overwhelmingly submit on phones. The multi-step form, upload, payment, and verdict views must be excellent on small screens with save-and-resume.
- **VC side: desktop-first.** The partner triages at a desk. The queue and side-by-side deal report are optimized for wide screens; on mobile they collapse to a readable single-column review mode (view and decide, not the primary workspace).

## Accessibility Requirements

- **WCAG 2.1 AA.** Body and UI text at ≥ 4.5:1 contrast; large text and non-text UI at ≥ 3:1.
- **Color is never the only signal.** The green/yellow/red system must always pair color with a text label and a distinct icon/shape — the whole product leans on this signal, and colorblind users and low-quality displays cannot be excluded.
- **Keyboard operable.** Full keyboard navigation through the queue, forms, and decision actions; visible focus states throughout.
- **Focus management** in the multi-step form (announce step changes) and in the deal report.
- **Screen-reader labels** for all status, color tags, and async states.
- **Localization-ready.** English first, with Uzbek/Russian likely — design for ~30% text expansion and avoid text baked into images.

## Out of Scope

- **AI quality itself** — prompt design, model choice, and summary accuracy are product/ML concerns, not this UI brief. The interface assumes outputs exist and focuses on framing them honestly.
- **Payment/billing depth** — the validation-fee step is a stub for the pilot; full billing, refunds, and receipts come later.
- **Multi-VC / multi-country** — single partner, single country. No tenancy, org admin, or per-firm configuration. (Deliberate: strategy says prove one country with one external VC before scaling.)
- **Texas partner portal** — US intros happen off-platform, human-to-human, for now. No investor-facing accounts.
- **Full CRM / pipeline management** — no deal stages beyond the single triage loop, no notes threads, no analytics dashboards.
- **Founder marketplace / discovery** — founders don't browse investors; this is a curated pipe, not a two-sided marketplace.
- **Full interface localization** — the *verdict* is translated into the founder's language, but the rest of the UI (forms, nav, VC workspace) stays English for the pilot. Whole-app localization comes later.
