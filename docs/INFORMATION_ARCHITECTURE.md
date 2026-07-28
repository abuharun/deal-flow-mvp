# Information Architecture: Deal-Flow MVP

*Derived from `DESIGN_BRIEF.md` (deal-flow-mvp). Greenfield — no existing routing to extend.*

**Structural decisions (locked):** one app, role-based routes (`/apply` founder, `/app` VC); email + password auth; the core object is a **Startup** everywhere; the VC works a **full Kanban pipeline** (backed by a searchable list so history isn't trapped in a board).

---

## Site Map

```
Public
- Landing / value prop            /
- Sign up                         /signup
- Log in                          /login
- Password reset                  /reset

Founder app  (role: founder)      /apply
- My Startup (status home)        /apply
- Submit / edit startup (stepped) /apply/submit        (steps via ?step=problem|product|market|traction|team|ask)
- Payment (validation fee)        /apply/submit/pay
- Verdict / response              /apply/verdict      (?lang=uz|ru|en)
- Verdict letter (PDF)            /apply/verdict/letter.pdf
- Account                         /apply/account

VC app  (role: vc)                /app
- Pipeline board (HOME, 80%)      /app
- Startups list (search/filter)   /app/startups
- Startup detail (review+decide)  /app/startups/[id]
- Account / settings              /app/settings
```

Role is resolved at login and lands the user in the correct root (`/apply` or `/app`). The two roots never share chrome.

## Navigation Model

**Founder side is nearly nav-free by design** — it's a linear flow, not a place to browse.

- **Primary navigation (founder)**: none in the traditional sense. After login the founder lands on *My Startup* (their status home). A single primary action changes with state: *Submit your startup* → *Continue* → *View verdict*.
- **Primary navigation (VC)**: two items only — **Pipeline** (the board) and **Startups** (the searchable list). The board is home. Keep it to these two for the pilot.
- **Secondary navigation (VC)**: within a Startup detail view, the AI summary / raw inputs / verification / decision are tabs or anchored sections, not separate routes.
- **Utility navigation**: account/settings and log-out, tucked top-right on both sides. Founder utility also holds billing history.
- **Mobile navigation**: Founder side is mobile-first and linear — a top progress indicator during submission, no menu. VC side is desktop-first; on mobile the Pipeline board collapses to a single vertical stack by stage, and primary nav becomes a bottom tab bar (Pipeline / Startups / Account).

## Content Hierarchy

### VC — Pipeline Board (home, 80% surface)
1. **The columns of Startups by stage** — the whole job is here; nothing should compete with it. Each card leads with the startup name, the color signal (label + icon, never color alone), and one line of AI summary.
2. **Color/priority within the New column** — the highest-signal items sort to the top so triage starts where it matters.
3. **Counts per stage** — lightweight orientation ("New 12 · In Review 3").
4. **Search / filter entry** — present but quiet; the board is for acting, the list is for finding.

### VC — Startup Detail (review + decide)
1. **AI summary beside the founder's raw inputs** — side by side, so nothing generated hides what was actually submitted. This is the trust principle made literal.
2. **The recommendation** — clearly framed as guidance, not verdict.
3. **Verification checklist** — the human proof-check (revenue, cap table, references), because the VC's name rides on the decision.
4. **Decision action bar** — pick action (Recommend / Pass / Advance-to-US) + a **rough-notes** field for blunt reasoning.
5. **Verdict composer** — one action turns the rough notes into a structured, official verdict in the founder's language (English original kept). The VC edits the polished draft in place; an explicit **Send** dispatches it — nothing auto-sends. Below it, the attachments/links (deck, data room).

### Founder — My Startup (status home)
1. **Current status, in plain warm language** — "Under review," "Decision ready." The one thing they logged in to see.
2. **Primary next action** — continue submission, pay, or view verdict, depending on state.
3. **Their submitted startup summary** — collapsed, expandable.

### Founder — Verdict
1. **The verdict and its reason** — honest, warm, specific, in the founder's own language.
2. **What would change the answer** — the constructive path forward, where relevant.
3. **Next steps** — only shown if advanced toward a US intro.
4. **Download official letter (PDF)** and a quiet toggle to view the **English original**.

## User Flows

### Founder: submit a startup
1. Lands on `/` → **Sign up** (email + password).
2. Lands on **My Startup** (empty) → primary action *Submit your startup*.
3. Steps through the form (problem → product → market → traction → team → ask), save-and-resume at each step.
   - If they leave → progress saved; return lands on the next incomplete step.
4. **Payment** for validation.
   - If payment fails → held at pay step, startup not yet submitted.
   - If payment succeeds → startup enters the VC pipeline as **New**; founder sees a warm "under review" state with honest timing.
5. Later, founder returns → **My Startup** shows *Decision ready* → **Verdict**.

### VC: triage and decide
1. Log in → **Pipeline board**, New column color-sorted.
2. Open a card → **Startup detail**; card moves to **In Review**.
3. Review AI summary against raw inputs; work the **verification checklist**; optionally re-tag the color signal.
4. Pick an action and write **rough notes** for the reasoning:
   - **Recommend** → will land in *Recommended*.
   - **Advance to US** → will land in *Advanced*; intro handled off-platform.
   - **Pass** → will land in *Passed*.
5. Trigger the **verdict composer** → AI structures and polishes the notes into an official verdict in the founder's language (English original retained).
   - VC edits the draft in place; can re-run the composer after tweaking notes.
   - VC clicks **Send** — the only thing that dispatches to the founder. Nothing auto-sends.
6. Card moves to its stage; founder is notified; **outcome recorded** (feeds the strategy's outcome-tracking loop). The generated PDF letter is stored on the Startup record.

## Naming Conventions

| Concept | Label in UI | Notes |
|---------|-------------|-------|
| The company being evaluated | **Startup** | One word everywhere, both roles. |
| Founder's act of entering their startup | **Submit** / *Submit your startup* | Not "apply" — keeps the single object model. |
| The VC's whole workspace | **Pipeline** | The board is *the* Pipeline. |
| Kanban stages | **New**, **In Review**, **Recommended**, **Advanced**, **Passed** | Linear left-to-right; Passed is a collapsed/filterable column. |
| Green/yellow/red priority | **Signal** | Always label + icon + color; "high/medium/low signal." Never a score, never a verdict. |
| AI's suggested read | **Recommendation** | Explicitly framed as guidance. |
| Human proof-check step | **Verification** | Checklist, VC-owned. |
| The founder-facing outcome | **Verdict** | Warm, honest, reasoned. |
| Send a startup toward US capital | **Advance to US** | Consistent verb for the Texas hand-off. |
| VC's blunt reasoning input | **Notes** | Rough and unpolished; never shown to the founder. |
| AI cleanup of notes into official text | **Compose verdict** / **Polish** | Draft assistant; the VC remains author of record. |
| The downloadable official document | **Verdict letter** | Branded, dated PDF — the official artifact. |

## Component Reuse Map

| Component | Used on | Behavior differences |
|-----------|---------|---------------------|
| Root layout + auth guard | All authenticated routes | Branches chrome by role (founder vs VC). |
| Founder linear layout | `/apply/*` | Progress header, no nav menu; mobile-first. |
| VC app shell | `/app/*` | Two-item primary nav + utility; desktop-first, bottom tabs on mobile. |
| Startup card | Board, Startups list | Compact on board, row form in list. |
| Signal tag | Card, detail, list | Identical rules everywhere: label + icon + color. |
| Stepped form | `/apply/submit` | Save-and-resume; one shared step wrapper. |
| Summary ⁄ raw split panel | Startup detail | Desktop side-by-side; stacks on mobile. |
| Verdict composer | Startup detail (VC) | AI polish of notes + inline editing; not present on the founder side. |
| Verdict view | Founder verdict, VC composer draft | Shared layout; the VC edits the draft, the founder reads the sent version. |
| Verdict-letter (PDF) generator | Startup detail (VC), Founder verdict | Produced on Send; stored on the Startup record; downloadable by both. |

## Content Growth Plan

- **Pipeline board** grows in the *New* and *Passed* columns fastest. Cap the board to active work: **New / In Review / Recommended / Advanced** stay on the board; **Passed** collapses behind a count and lives primarily in the **Startups list**.
- **Startups list** is the durable archive — paginated, full-text search over startup name and summary, filters by stage, signal, outcome, and date. This is where history and outcome-tracking live as volume climbs past a few hundred.
- **Founder side does not accumulate** — one founder, one startup (per cycle). No growth pattern needed beyond re-submission later.
- No analytics dashboards in the pilot; the Startups list with filters is the reporting surface.

## URL Strategy

- **Pattern**: `/[role-root]/[section]/[id]` — e.g. `/app/startups/[id]`.
- **Role roots**: `/apply` (founder), `/app` (VC). Public auth routes sit at the top level.
- **Dynamic segments**: `[id]` for a Startup (opaque UUID, not a guessable sequence, since these are confidential deals).
- **Query parameters**:
  - Submission step: `/apply/submit?step=traction`
  - Board is stable at `/app`; deep-linking a stage uses `/app?stage=in-review`.
  - List filtering/sorting/pagination on `/app/startups`: `?q=&stage=&signal=&outcome=&sort=&page=`.
  - Verdict language on the founder view: `/apply/verdict?lang=uz|ru|en` (defaults to the founder's language; English original always reachable).
- **Verdict letter**: served as `/apply/verdict/letter.pdf` for the founder; the same generated file is referenced on the Startup record for the VC. Auth-gated like everything else.
- **No public startup URLs.** Every Startup route requires the VC role; nothing about a founder's confidential submission is reachable without auth.
```

