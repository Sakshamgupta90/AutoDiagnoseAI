import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { config } from '@/config'
import { backend } from '@/lib/backend'
import { ApiError, toApiError } from '@/lib/errors'
import { uid } from '@/lib/format'
import type {
  AssistantMessage,
  AssistantStatus,
  Attachment,
  Conversation,
  UserMessage,
  VehicleContext,
} from '@/types/chat'
import type { Decision, DecisionPayload, DiagnosisEvent, FeedbackPayload } from '@/types/diagnosis'
import { useConnectionStore } from './connection'
import { useToastStore } from './toast'

const STORAGE_KEY = 'autodiagnose.conversations.v1'
const MAX_CONVERSATIONS = 40
const IN_FLIGHT: AssistantStatus[] = ['submitting', 'streaming', 'reconnecting', 'polling']

/* Non-serialisable runtime state lives outside the reactive store. */
const controllers = new Map<string, AbortController>()
const requestFiles = new Map<string, File[]>()

export const emptyVehicle = (): VehicleContext => ({ vin: '', make: '', model: '', dtc_codes: [] })
export const isInFlight = (s: AssistantStatus) => IN_FLIGHT.includes(s)

function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const list = JSON.parse(raw) as Conversation[]
    // Jobs that were running when the page closed can be reconnected, not silently lost.
    for (const c of list)
      for (const m of c.messages)
        if (m.role === 'assistant' && isInFlight(m.status)) {
          if (m.jobId) m.status = 'interrupted'
          else {
            m.status = 'error'
            m.error = { message: 'The page was closed before this request was sent.', retryable: true }
          }
        }
    return list
  } catch {
    return []
  }
}

function titleFor(text: string, vehicle: VehicleContext): string {
  const lead = vehicle.dtc_codes[0] ? `${vehicle.dtc_codes[0]} · ` : ''
  const body = text.replace(/#\w+/g, '').replace(/\s+/g, ' ').trim() || 'Photo inspection'
  const title = lead + body
  return title.length > 56 ? `${title.slice(0, 55)}…` : title
}

export interface SendInput {
  text: string
  vehicle: VehicleContext
  attachments: Attachment[]
  files: File[]
}

export const useChatStore = defineStore('chat', () => {
  const toast = useToastStore()
  const conversations = ref<Conversation[]>(loadConversations())
  const activeId = ref<string | null>(null)

  const active = computed(() => conversations.value.find((c) => c.id === activeId.value) ?? null)
  const sorted = computed(() => [...conversations.value].sort((a, b) => b.updatedAt - a.updatedAt))
  const activeBusy = computed(
    () => active.value?.messages.some((m) => m.role === 'assistant' && isInFlight(m.status)) ?? false,
  )

  /* ---------- persistence ---------- */
  let saveTimer: ReturnType<typeof setTimeout> | undefined
  let warnedQuota = false
  watch(
    conversations,
    (list) => {
      clearTimeout(saveTimer)
      saveTimer = setTimeout(() => {
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_CONVERSATIONS)))
        } catch {
          if (!warnedQuota) toast.warning('History not saved', 'Browser storage is full. Delete old diagnoses to keep new ones.')
          warnedQuota = true
        }
      }, 400)
    },
    { deep: true },
  )

  /* ---------- lookups ---------- */
  function findConversation(id: string) {
    return conversations.value.find((c) => c.id === id)
  }
  function findAssistant(convoId: string, msgId: string): AssistantMessage | undefined {
    const m = findConversation(convoId)?.messages.find((x) => x.id === msgId)
    return m?.role === 'assistant' ? m : undefined
  }
  function touch(convoId: string) {
    const c = findConversation(convoId)
    if (c) c.updatedAt = Date.now()
  }

  /* ---------- conversation management ---------- */
  function startNew() {
    activeId.value = null
  }
  function select(id: string) {
    activeId.value = id
  }
  function remove(id: string) {
    const c = findConversation(id)
    c?.messages.forEach((m) => controllers.get(m.id)?.abort())
    conversations.value = conversations.value.filter((x) => x.id !== id)
    if (activeId.value === id) activeId.value = null
  }
  function clearAll() {
    controllers.forEach((c) => c.abort())
    conversations.value = []
    activeId.value = null
  }

  /* ---------- event reducer ---------- */
  function applyEvent(msg: AssistantMessage, event: DiagnosisEvent) {
    const now = Date.now()
    const closeRunning = () =>
      msg.steps.forEach((s) => {
        if (s.status === 'running') Object.assign(s, { status: 'done', finishedAt: now })
      })

    switch (event.type) {
      case 'step':
        closeRunning()
        msg.steps.push({ ...event.data, key_inputs: event.data.key_inputs ?? {}, status: 'running', startedAt: now, evidence: [] })
        break
      case 'evidence': {
        const target = msg.steps.at(-1)
        if (target && !target.evidence.some((e) => e.chunk_id === event.data.chunk_id && e.source === event.data.source))
          target.evidence.push(event.data)
        break
      }
      case 'confidence': {
        const v = Math.min(1, Math.max(0, Number(event.data.value) || 0))
        msg.confidence = v
        msg.confidenceHistory.push(v)
        break
      }
      case 'escalation':
        msg.escalation = event.data
        break
      case 'notice':
        if (!msg.notices.some((n) => n.kind === event.data.kind)) msg.notices.push(event.data)
        break
      case 'done': {
        closeRunning()
        msg.diagnosis = event.data
        const top = event.data.ranked_causes[0]?.confidence
        if (msg.confidence === null && top !== undefined) msg.confidence = top
        if (event.data.fallback_mode && !msg.notices.some((n) => n.kind === 'cloud_unreachable'))
          msg.notices.push({ kind: 'cloud_unreachable', message: 'This result came from the local keyword fallback because AWS Bedrock was unreachable.' })
        break
      }
      case 'error':
        break // handled by the transport
    }
  }

  /* ---------- job lifecycle ---------- */
  async function run(convoId: string, msgId: string, resumeJobId?: string) {
    const get = () => findAssistant(convoId, msgId)
    const msg = get()
    const convo = findConversation(convoId)
    if (!msg || !convo) return
    const request = convo.messages.find((m) => m.id === msg.requestId) as UserMessage | undefined
    if (!request) return

    const ctrl = new AbortController()
    controllers.set(msgId, ctrl)
    const watchdog = setTimeout(
      () => ctrl.abort(new ApiError('No final answer arrived in time. The server may be overloaded — try again.', { code: 'timeout' })),
      config.clientTimeoutMs,
    )

    try {
      let jobId = resumeJobId
      if (!jobId) {
        msg.status = 'submitting'
        const v = request.vehicle
        const res = await backend.createDiagnosis(
          {
            vin: v.vin || undefined,
            make: v.make || undefined,
            model: v.model || undefined,
            dtc_codes: v.dtc_codes,
            symptom_text: request.text,
            photos: requestFiles.get(request.id) ?? [],
            session_id: convoId,
          },
          ctrl.signal,
        )
        jobId = res.job_id
        get()!.jobId = jobId
      }

      get()!.status = 'streaming'
      await backend.streamEvents(
        jobId,
        {
          onEvent: (e) => {
            const m = get()
            if (m) applyEvent(m, e)
          },
          onConnectionChange: (state, attempt) => {
            const m = get()
            if (!m) return
            m.status = state === 'reconnecting' ? 'reconnecting' : state === 'polling' ? 'polling' : 'streaming'
            m.reconnectAttempt = attempt
          },
        },
        ctrl.signal,
      )

      const m = get()
      if (!m) return
      if (!m.diagnosis) throw new ApiError('The diagnosis ended without a result.', { code: 'incomplete' })
      m.status = 'complete'
      if (m.diagnosis.escalation_required && document.hidden)
        toast.warning('Sign-off needed', 'A diagnosis is waiting for senior technician approval.')
    } catch (err) {
      const m = get()
      if (!m) return
      const reason = ctrl.signal.reason
      if (ctrl.signal.aborted && !(reason instanceof ApiError)) {
        m.status = 'cancelled'
      } else {
        const e = reason instanceof ApiError ? reason : toApiError(err)
        m.status = 'error'
        m.error = { message: e.message, retryable: e.retryable }
      }
    } finally {
      clearTimeout(watchdog)
      controllers.delete(msgId)
      const m = get()
      if (m) m.finishedAt = Date.now()
      touch(convoId)
      useConnectionStore().check() // reflect whether the AI model answered
    }
  }

  function newAssistant(requestId: string): AssistantMessage {
    return {
      id: uid('a'),
      role: 'assistant',
      requestId,
      status: 'submitting',
      steps: [],
      confidence: null,
      confidenceHistory: [],
      notices: [],
      startedAt: Date.now(),
    }
  }

  /** Swap in a fresh assistant message with the same id, clearing any previous result. */
  function replaceAssistant(convoId: string, msgId: string, patch: Partial<AssistantMessage> = {}) {
    const convo = findConversation(convoId)
    const i = convo?.messages.findIndex((m) => m.id === msgId) ?? -1
    const old = convo?.messages[i]
    if (!convo || old?.role !== 'assistant') return
    convo.messages.splice(i, 1, { ...newAssistant(old.requestId), id: msgId, ...patch })
  }

  async function send(input: SendInput) {
    if (activeBusy.value) return
    let convo = active.value
    if (!convo) {
      const now = Date.now()
      conversations.value.unshift({
        id: uid('c'),
        title: titleFor(input.text, input.vehicle),
        createdAt: now,
        updatedAt: now,
        vehicle: input.vehicle,
        messages: [],
      })
      convo = conversations.value[0]
      activeId.value = convo.id
    }
    convo.vehicle = { ...input.vehicle, dtc_codes: [...input.vehicle.dtc_codes] }

    const user: UserMessage = {
      id: uid('u'),
      role: 'user',
      text: input.text,
      attachments: input.attachments,
      vehicle: { ...input.vehicle, dtc_codes: [...input.vehicle.dtc_codes] },
      createdAt: Date.now(),
    }
    requestFiles.set(user.id, input.files)
    const assistant = newAssistant(user.id)
    convo.messages.push(user, assistant)
    touch(convo.id)
    await run(convo.id, assistant.id)
  }

  function cancel(msgId: string) {
    controllers.get(msgId)?.abort()
  }

  function cancelActive() {
    active.value?.messages.forEach((m) => controllers.get(m.id)?.abort())
  }

  async function retry(convoId: string, msgId: string) {
    const msg = findAssistant(convoId, msgId)
    if (!msg || isInFlight(msg.status)) return
    const convo = findConversation(convoId)!
    const request = convo.messages.find((m) => m.id === msg.requestId) as UserMessage | undefined
    if (request?.attachments.length && !requestFiles.has(request.id))
      toast.warning('Retrying without photos', 'Photos from an earlier session aren’t kept in the browser. Attach them again for a photo-based diagnosis.')
    replaceAssistant(convoId, msgId)
    await run(convoId, msgId)
  }

  async function resume(convoId: string, msgId: string) {
    const msg = findAssistant(convoId, msgId)
    if (!msg?.jobId) return retry(convoId, msgId)
    const jobId = msg.jobId
    replaceAssistant(convoId, msgId, { jobId, status: 'streaming' })
    await run(convoId, msgId, jobId)
  }

  async function decide(convoId: string, msgId: string, decision: Decision, payload: DecisionPayload, senior: boolean) {
    const msg = findAssistant(convoId, msgId)
    if (!msg?.jobId) return false
    try {
      await backend.decide(msg.jobId, decision, payload)
      findAssistant(convoId, msgId)!.decision = {
        decision: decision === 'approve' ? 'approved' : 'rejected',
        by: payload.technician_id,
        notes: payload.notes,
        at: Date.now(),
        senior,
      }
      touch(convoId)
      toast.success(decision === 'approve' ? (senior ? 'Plan approved and released' : 'Diagnosis accepted') : 'Diagnosis rejected')
      return true
    } catch (err) {
      toast.error('Couldn’t record the decision', toApiError(err).message)
      return false
    }
  }

  async function submitFeedback(convoId: string, msgId: string, payload: FeedbackPayload) {
    const msg = findAssistant(convoId, msgId)
    if (!msg?.jobId) return false
    try {
      await backend.submitFeedback(msg.jobId, payload)
      findAssistant(convoId, msgId)!.feedback = { ...payload, at: Date.now() }
      touch(convoId)
      toast.success('Job closed', 'The confirmed fix was added to the workshop knowledge base.')
      return true
    } catch (err) {
      toast.error('Couldn’t save feedback', toApiError(err).message)
      return false
    }
  }

  return {
    conversations,
    sorted,
    activeId,
    active,
    activeBusy,
    startNew,
    select,
    remove,
    clearAll,
    send,
    cancel,
    cancelActive,
    retry,
    resume,
    decide,
    submitFeedback,
  }
})
