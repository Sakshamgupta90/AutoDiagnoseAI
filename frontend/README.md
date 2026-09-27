# AutoDiagnose AI — Technician Dashboard

The Vue 3 frontend for AutoDiagnose AI: a chat interface where technicians submit symptoms, VIN or chassis numbers, OBD-II fault codes and inspection photos, then follow the agent's reasoning live.

**Stack:** Vue 3 · TypeScript · Vite · Tailwind CSS v4 · Pinia · Vitest

## Development

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # unit tests
npm run build      # type-check and production build into dist/
```

Create `.env.local` to choose the backend:

| Variable | Example | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | API base URL. In production it is `/api/v1`, on the same origin. |
| `VITE_USE_MOCK` | `false` | `true` runs against the built-in mock backend (no server required) |
| `VITE_HEALTH_PATH` | `/health` | Polled for the connection indicator |
| `VITE_CURRENCY` | `SGD` | Currency for estimates |

## Features

- **Multimodal composer:**
  - Symptom text.
  - VIN and chassis-number checks.
  - OBD-II fault-code chips.
  - Up to 4 photos by picker, camera, drag-and-drop or paste. Photos are resized and re-encoded in the browser, which strips EXIF and GPS data.
- **Live reasoning trace:** typed Server-Sent Events rendered as steps, each with its cited evidence. A confidence meter and the agent's turn, tool and time budget are shown alongside.
- **Diagnosis report:**
  - Ranked causes with their sources.
  - A checklist of confirmation tests.
  - A parts and labour estimate.
  - Safety flags, and a badge showing what the answer is based on.
  - Copy and print.
- **Human in the loop:**
  - Senior sign-off before safety-critical plans are revealed.
  - Low-confidence review.
  - Accept or reject.
  - A close-job form that feeds the confirmed fix back into the knowledge base.
- **Resilience:**
  - Reconnects with `Last-Event-ID` and falls back to polling.
  - A client-side time limit, and a stop button.
  - Resumes interrupted jobs after a reload.
  - Offline and backend-down banners.
  - Readable error messages mapped from HTTP status codes.
- **UX:**
  - Responsive layout with a mobile drawer.
  - Light, dark and system themes.
  - Chat history saved in `localStorage` and searchable.
  - Keyboard shortcuts, screen-reader labels, and support for reduced motion.

## Structure

```
src/
  config.ts          limits, agent budget, environment
  types/             API contract and chat state types
  lib/               API client (fetch + SSE), mock backend, SSE parser, image and input validation
  stores/            Pinia stores: chat and job lifecycle, connection, toasts, UI
  components/        app shell, composer, reasoning trace, report, approval and feedback panels
```
