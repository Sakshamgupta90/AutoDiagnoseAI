const env = import.meta.env

const apiBaseUrl = (env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')

export const config = {
  apiBaseUrl,
  /** Mock mode when explicitly requested, or when no backend URL is configured. */
  useMock: env.VITE_USE_MOCK === 'true' || apiBaseUrl === '',
  healthPath: env.VITE_HEALTH_PATH || '/health',
  currency: env.VITE_CURRENCY || 'SGD',

  /** Upload limits (client-side guard; the backend re-validates). */
  maxPhotos: 4,
  maxPhotoBytes: 15 * 1024 * 1024,
  /** Photos are downscaled to this long edge and re-encoded (also strips EXIF/GPS). */
  photoMaxEdge: 1600,
  photoQuality: 0.85,

  maxSymptomChars: 2000,
  maxDtcCodes: 8,

  /** Mirrors the orchestrator budget (Section 3.2) so the UI can show progress. */
  budget: { turns: 3, toolCalls: 6, seconds: 45 },
  /** Client watchdog: give up if no final answer well after the server budget. */
  clientTimeoutMs: 90_000,
  requestTimeoutMs: 30_000,
  /** Heartbeats arrive every 15s; treat 40s of silence as a dropped stream. */
  streamIdleMs: 40_000,
  streamMaxReconnects: 3,
  pollIntervalMs: 2_000,

  /** Below this, the plan is framed as "insufficient evidence" (Section 7.1). */
  confidenceThreshold: 0.5,
} as const
