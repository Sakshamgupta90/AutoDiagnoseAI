import { config } from '@/config'
import type { Diagnosis, DiagnosisEvent, JobSnapshot } from '@/types/diagnosis'
import type { DiagnosisBackend, StreamHandlers } from './backend'
import { ApiError, errorFromResponse, isAbortError, toApiError } from './errors'
import { createSSEParser, type SSEMessage } from './sse'

const EVENT_TYPES = new Set(['step', 'evidence', 'confidence', 'escalation', 'notice', 'error', 'done'])

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason)
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => (clearTimeout(t), reject(signal.reason)), { once: true })
  })
}

function withTimeout(signal: AbortSignal | undefined, ms: number): AbortSignal {
  const timeout = AbortSignal.timeout(ms)
  return signal ? AbortSignal.any([signal, timeout]) : timeout
}

function parseEvent(msg: SSEMessage): DiagnosisEvent | null {
  if (!EVENT_TYPES.has(msg.event)) return null
  try {
    return { type: msg.event, data: JSON.parse(msg.data) } as DiagnosisEvent
  } catch {
    console.warn('[sse] ignoring malformed event payload', msg)
    return null
  }
}

export function createLiveBackend(baseUrl: string): DiagnosisBackend {
  async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
    const { timeoutMs = config.requestTimeoutMs, signal, ...rest } = init
    let res: Response
    try {
      res = await fetch(`${baseUrl}${path}`, {
        ...rest,
        headers: { Accept: 'application/json', ...rest.headers },
        signal: withTimeout(signal ?? undefined, timeoutMs),
      })
    } catch (err) {
      if (signal?.aborted) throw err
      throw toApiError(err)
    }
    if (!res.ok) throw await errorFromResponse(res)
    if (res.status === 204) return undefined as T
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }

  /**
   * One SSE connection over fetch (GET, no body — same as EventSource, but
   * lets us read HTTP errors and add auth headers later). Returns true once
   * the `done` event arrives, false if the connection closed early.
   */
  async function openStream(
    jobId: string,
    handlers: StreamHandlers,
    signal: AbortSignal,
    lastEventId: { value?: string },
  ): Promise<boolean> {
    const idle = new AbortController()
    const combined = AbortSignal.any([signal, idle.signal])
    let idleTimer = setTimeout(() => idle.abort(), config.streamIdleMs)
    const bump = () => {
      clearTimeout(idleTimer)
      idleTimer = setTimeout(() => idle.abort(), config.streamIdleMs)
    }

    try {
      const headers: Record<string, string> = { Accept: 'text/event-stream', 'Cache-Control': 'no-cache' }
      if (lastEventId.value) headers['Last-Event-ID'] = lastEventId.value
      const res = await fetch(`${baseUrl}/diagnoses/${encodeURIComponent(jobId)}/events`, { headers, signal: combined })
      if (!res.ok) throw await errorFromResponse(res)
      if (!res.body) throw new ApiError('This browser does not support streaming responses.', { code: 'stream', retryable: false })

      handlers.onConnectionChange?.('open')
      let finished = false
      let streamError: ApiError | null = null
      const parser = createSSEParser({
        onComment: bump,
        onMessage: (msg) => {
          bump()
          if (msg.id) lastEventId.value = msg.id
          const event = parseEvent(msg)
          if (!event) return
          if (event.type === 'error') {
            streamError = new ApiError(event.data.message || 'The diagnosis failed on the server.', {
              code: 'server',
              retryable: event.data.retryable ?? true,
            })
            return
          }
          handlers.onEvent(event)
          if (event.type === 'done') finished = true
        },
      })

      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      while (!finished && !streamError) {
        const { value, done } = await reader.read()
        if (done) break
        bump()
        parser.push(value)
      }
      parser.push('\n\n') // flush a trailing event without a blank line
      await reader.cancel().catch(() => {})
      if (streamError) throw streamError
      return finished
    } catch (err) {
      if (signal.aborted) throw err
      if (err instanceof ApiError) throw err
      if (idle.signal.aborted || isAbortError(err) || err instanceof TypeError) return false // dropped: reconnect
      throw toApiError(err)
    } finally {
      clearTimeout(idleTimer)
    }
  }

  async function pollUntilDone(jobId: string, handlers: StreamHandlers, signal: AbortSignal) {
    handlers.onConnectionChange?.('polling')
    for (;;) {
      const snap = await request<JobSnapshot>(`/diagnoses/${encodeURIComponent(jobId)}`, { signal })
      if (snap.diagnosis) {
        handlers.onEvent({ type: 'done', data: snap.diagnosis as Diagnosis })
        return
      }
      if (snap.status === 'failed')
        throw new ApiError(snap.error || 'The diagnosis failed on the server.', { code: 'server' })
      await sleep(config.pollIntervalMs, signal)
    }
  }

  return {
    mode: 'live',

    async health(signal) {
      try {
        // Any HTTP response means the service is reachable, even if /health isn't implemented.
        const res = await fetch(`${baseUrl}${config.healthPath}`, { signal: withTimeout(signal, 5000) })
        let llmAvailable: boolean | null = null
        try {
          const body = await res.json()
          if (typeof body?.llm?.available === 'boolean') llmAvailable = body.llm.available
        } catch {
          /* non-JSON health response */
        }
        return { reachable: true, llmAvailable }
      } catch {
        return { reachable: false, llmAvailable: null }
      }
    },

    createDiagnosis(req, signal) {
      const form = new FormData()
      if (req.vin) form.append('vin', req.vin)
      if (req.make) form.append('make', req.make)
      if (req.model) form.append('model', req.model)
      req.dtc_codes.forEach((code) => form.append('dtc_codes', code))
      form.append('symptom_text', req.symptom_text)
      req.photos.forEach((photo) => form.append('photos', photo, photo.name))
      if (req.session_id) form.append('session_id', req.session_id)
      return request('/diagnoses', { method: 'POST', body: form, signal, timeoutMs: 60_000 })
    },

    async streamEvents(jobId, handlers, signal) {
      const lastEventId: { value?: string } = {}
      for (let attempt = 0; ; attempt++) {
        handlers.onConnectionChange?.(attempt === 0 ? 'connecting' : 'reconnecting', attempt)
        const finished = await openStream(jobId, handlers, signal, lastEventId)
        if (finished) return
        if (attempt >= config.streamMaxReconnects) break
        await sleep(Math.min(1000 * 2 ** attempt, 8000), signal)
      }
      // The stream keeps dropping (proxy buffering, flaky network): fall back to polling.
      await pollUntilDone(jobId, handlers, signal)
    },

    getDiagnosis(jobId, signal) {
      return request(`/diagnoses/${encodeURIComponent(jobId)}`, { signal })
    },

    async decide(jobId, decision, payload) {
      await request(`/diagnoses/${encodeURIComponent(jobId)}/${decision}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    },

    async submitFeedback(jobId, payload) {
      await request(`/diagnoses/${encodeURIComponent(jobId)}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    },
  }
}
