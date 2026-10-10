# Bvosita scraper UI

A static Next.js interface for operating Bvosita’s university programme research workflow. The app reproduces the supplied Clay-inspired design in `design/bvosita.html` and uses realistic, typed mock data. It does not call a backend, authenticate against a service, crawl websites, or upload files.

## Run locally

Node.js 20 or newer is recommended.

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. The sign-in form is a frontend-only demo. Submitting it, like every control that would normally mutate remote data, shows a “Not connected yet” toast and changes nothing.

## Quality checks and static export

```bash
npm run lint
npm run build
```

`npm run build` creates the deployable static site in `out/`. The app uses trailing-slash URLs and unoptimized local images so it can be hosted by a static web server. No server runtime is required.

## Routes

- `/login` — single-user sign-in
- `/` — dashboard
- `/import` — workbook import and mapping
- `/universities` — filterable university table; `?state=empty|loading|error` previews states
- `/universities/[id]` — programme and change history
- `/runs/new` — configure a manual research run
- `/schedules` — recurring run list and editor; `?state=empty|loading|error` previews states
- `/review/[runId]` — results and changes review; `?state=empty|loading|error` previews states
- `/export` — export builder, preview, and history
- `/settings` — crawler, provider, freshness, and retention settings

There is intentionally no run-monitor or `/runs/[id]` route. Recent dashboard runs are informational rows; review links use `/review/[runId]`.

## Frontend architecture

- `app/` contains App Router pages and the shared global design system.
- `components/` contains reusable shell, navigation, tables, state views, overlays, status chips, progress, and toast feedback.
- `lib/types.ts` is the domain model.
- `lib/mock/data.ts` contains fixtures.
- `lib/data.ts` is the only public data-access boundary used by the UI.

The legacy `src/`, `backend/`, and end-to-end folders are excluded from this static frontend build and were not changed as part of this UI replacement.

## Design fidelity and documented differences

`design/bvosita.html` is the source of truth for layout, spacing, typography, colours, components, and copy. The supplied screenshots were used as visual checks. The implementation intentionally differs only where the approved product instructions override the source design:

- The source design includes a Run Monitor screen. It is omitted by owner request: there is no `/runs/[id]` route, dashboard run rows are informational rather than links, and review navigation uses `/review/[runId]`.
- The login reference’s inline incorrect-password example is retained as static design copy. Because this build has no authentication and action controls must not change state, selecting Sign in additionally shows the standard “Not connected yet” toast without validating or navigating.
- Native form controls and semantic tables are used where the design export represented controls as styled `div` elements, preserving the visual treatment while making controls labelled and keyboard reachable.

No other known HTML-versus-screenshot differences were introduced.
