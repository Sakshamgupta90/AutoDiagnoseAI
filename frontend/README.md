# AutoDiagnose AI — Technician Dashboard (frontend)

This is the chat interface for the AutoDiagnose AI vehicle fault diagnosis agent. A technician describes the symptoms and can add a VIN, OBD-II fault codes and inspection photos. The agent's reasoning streams back live, one step at a time. The final result shows:

- ranked causes, each citing its source
- confirmation tests
- a parts and labour estimate
- a senior-technician sign-off gate for safety-critical faults

**Stack:** Vue 3 · TypeScript · Vite · Tailwind CSS v4 · Pinia · lucide icons · Vitest. This is the Vue + Tailwind stack named in the architecture document.

## Quick start

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (uses the built-in mock backend)
npm test             # unit tests
npm run build        # type-check + production build into dist/
```

With no `VITE_API_BASE_URL` set, the app runs against a mock backend in the browser. The mock follows the frozen API contract exactly, so the whole UI works before the FastAPI service is live.

### Demo triggers (mock mode)

Add these tags to the symptom text to demo the resilience paths:

| Tag | What it shows |
|---|---|
| `#error` | Job creation fails, then the error card appears with Retry and Edit & resend |
| `#drop` | The SSE stream drops mid-diagnosis and reconnects automatically |
| `#offline` | AWS Bedrock is unreachable, so the "Cloud Unreachable" banner appears with the local keyword fallback |

The keywords in the text choose the scenario:

| Keywords | Scenario |
|---|---|
| misfire / `P0301` | Normal diagnosis |
| brake / grinding | Safety-critical: the plan is locked until a senior technician signs off |
| overheating | Normal diagnosis |
| slow crank | Electrical fault |
| Anything vague | Low confidence: "insufficient evidence, run these tests first" |

## Environment variables

Copy `.env.example` to `.env.local` to set these locally, or set them in Vercel.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | *(empty)* | FastAPI base URL, e.g. `https://api.example.com`. If empty, the mock is used. |
| `VITE_USE_MOCK` | `false` | Set to `true` to force the mock even when a URL is set |
| `VITE_HEALTH_PATH` | `/health` | Pinged every 30 s for the header connection indicator |
| `VITE_CURRENCY` | `SGD` | Currency for the estimates |

## Backend contract (Architecture §4 and §6, frozen 18 Sep)

| # | Call | Used for |
|---|---|---|
| 1 | `POST /diagnoses`: multipart with `vin`, `make`, `model`, `dtc_codes` (repeated), `symptom_text`, `photos` (repeated) → `202 {job_id, status}` | Sending the request |
| 2 | `GET /diagnoses/{id}/events` with `text/event-stream` | Live reasoning trace |
| 3 | `GET /diagnoses/{id}` | Fallback when the stream keeps dropping (after 3 reconnects) |
| 4 | `POST /diagnoses/{id}/approve` or `/reject` with body `{technician_id, notes?}` | Human-in-the-loop decision |
| 5 | `POST /diagnoses/{id}/feedback` with body `{confirmed_cause, confirmed_fix, part_cost?, labour_hours?}` | Closing the job and feeding the knowledge base |

The SSE events handled are `step`, `evidence`, `confidence`, `escalation` and `done`, plus `: heartbeat` comments. The TypeScript definitions are in [`src/types/diagnosis.ts`](src/types/diagnosis.ts).

The UI also understands these optional extensions. The backend can add them but doesn't have to:

- a `notice` event: `{kind: "cloud_unreachable" | "budget_exhausted", message}`
- an `error` event: `{message, retryable}`
- a `session_id` form field, which groups follow-up messages
- `summary`, `fallback_mode` and `budget_exhausted` fields on the final diagnosis

### Notes for the FastAPI side

- **CORS:** allow the Vercel origin (e.g. `https://autodiagnose.vercel.app`) for `GET` and `POST`.
- **SSE response headers:** `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`. In nginx, also set `proxy_buffering off`.
- **Heartbeat:** send `: heartbeat\n\n` every 15 s. The client treats 40 s of silence as a dropped connection.
- **HTTPS:** the backend must be served over HTTPS. An HTTPS Vercel page cannot call an `http://` Lightsail IP, because browsers block mixed content.
- **Errors:** FastAPI's `{"detail": ...}` error bodies are shown to the technician as readable messages.

## Features and how they map to the architecture

- **Split POST + SSE flow (W4).** The stream is read over `fetch`, so HTTP errors are visible and auth headers can be added later. It reconnects with backoff and `Last-Event-ID`, then falls back to polling (`src/lib/api.ts`).
- **Typed trace, not raw chain-of-thought (W8).** Each tool call is a step showing its key inputs and the evidence it retrieved. A live confidence meter with a sparkline and a budget bar (3 turns / 6 tools / 45 s) sit alongside.
- **Human-in-the-loop (M3).**
  - Brakes, steering, airbag and EV high-voltage plans are *not rendered* until a senior technician approves them.
  - Low-confidence answers are framed as "insufficient evidence".
  - Every job is accepted or rejected, and rejecting requires a note.
- **Feedback loop (M7).** When a job closes, the confirmed cause and fix are sent to `/feedback`.
- **Photo privacy and cost (§7.2).** Photos are downscaled to 1600 px and re-encoded in the browser. This strips all EXIF data, including GPS, and cuts upload size (a 3.5 MB photo becomes about 35 KB). HEIC files get a friendly error.
- **Input validation:**
  - VINs are checked for 17 characters with no I, O or Q.
  - Shorter chassis numbers from parallel imports are accepted, with a hint to add make and model.
  - DTCs are entered as chips and validated as OBD-II codes.
- **Error handling:**
  - Offline and backend-down banner.
  - Per-message error cards with retry and edit.
  - Timeouts, plus a 90 s client watchdog.
  - Stop and cancel.
  - Reconnecting to a job that was running when the page was reloaded.
  - Readable error messages mapped from HTTP status codes.
- **History:** kept in `localStorage`, with search, status badges and delete.
- **UX:**
  - Responsive from 320 px up, with a mobile drawer and a camera capture button.
  - Light, dark and system themes.
  - Drag, drop or paste photos, with a lightbox to view them.
  - Keyboard shortcuts: Enter to send, Shift+Enter for a new line, Ctrl/⌘+Shift+O for a new diagnosis.
  - Screen-reader labels, live regions, and support for reduced motion.
  - Copy and print for the report.

## Project structure

```
src/
  config.ts              # limits, budget, env
  types/                 # API contract + chat state types
  lib/
    api.ts               # live FastAPI client (fetch + SSE, reconnect, polling)
    mock.ts              # contract-faithful mock orchestrator
    backend.ts           # picks live vs mock
    sse.ts               # incremental text/event-stream parser
    image.ts             # validate, downscale, strip EXIF
    validators.ts        # VIN / DTC
    errors.ts            # ApiError + readable HTTP error messages
  stores/                # Pinia: chat (job lifecycle), toast, ui, connection
  components/            # App shell, composer, trace, report, approval gate…
```

## Deploying to Vercel

1. Push the repo to GitHub.
2. In Vercel, click **Add New… → Project** and import `AutoDiagnoseAI`.
3. Set **Root Directory** to `frontend`. Vercel detects Vite, and `vercel.json` already sets the build command, the output folder, SPA rewrites and security headers.
4. Under **Environment Variables**, set `VITE_API_BASE_URL` once the backend is live. Leave it empty for a mock-mode demo.
5. Click **Deploy**. Each push to `main` redeploys automatically.

To deploy from the command line instead:

```bash
npm i -g vercel
cd frontend
vercel          # first run links the project; accept the detected Vite settings
vercel --prod
```

`VITE_*` variables are baked in at build time. After changing one in Vercel, redeploy.
