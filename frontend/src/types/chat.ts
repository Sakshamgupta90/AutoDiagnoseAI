import type {
  Diagnosis,
  EscalationEventData,
  EvidenceEventData,
  FeedbackPayload,
  NoticeEventData,
  StepEventData,
} from './diagnosis'

export interface VehicleContext {
  vin: string
  make: string
  model: string
  dtc_codes: string[]
}

export interface Attachment {
  id: string
  name: string
  size: number
  width: number
  height: number
  /** Small JPEG data URL, persisted with history. */
  thumbUrl: string
}

export interface UserMessage {
  id: string
  role: 'user'
  text: string
  attachments: Attachment[]
  vehicle: VehicleContext
  createdAt: number
}

export type AssistantStatus =
  | 'submitting'
  | 'streaming'
  | 'reconnecting'
  | 'polling'
  | 'complete'
  | 'error'
  | 'cancelled'
  /** The page was reloaded while this job was running. */
  | 'interrupted'

export interface TraceStep extends StepEventData {
  status: 'running' | 'done'
  startedAt: number
  finishedAt?: number
  evidence: EvidenceEventData[]
}

export interface DecisionRecord {
  decision: 'approved' | 'rejected'
  by: string
  notes?: string
  at: number
  /** Whether this was the senior sign-off gate for a safety-critical plan. */
  senior: boolean
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  /** The user message this answers — used for retries. */
  requestId: string
  jobId?: string
  status: AssistantStatus
  reconnectAttempt?: number
  steps: TraceStep[]
  confidence: number | null
  confidenceHistory: number[]
  escalation?: EscalationEventData
  notices: NoticeEventData[]
  diagnosis?: Diagnosis
  error?: { message: string; retryable: boolean }
  decision?: DecisionRecord
  feedback?: FeedbackPayload & { at: number }
  startedAt: number
  finishedAt?: number
}

export type ChatMessage = UserMessage | AssistantMessage

export interface Conversation {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  vehicle: VehicleContext
  messages: ChatMessage[]
}
