import { config } from '@/config'
import type {
  CreateDiagnosisResponse,
  Decision,
  DecisionPayload,
  DiagnosisEvent,
  DiagnosisRequest,
  FeedbackPayload,
  JobSnapshot,
} from '@/types/diagnosis'
import { createLiveBackend } from './api'
import { createMockBackend } from './mock'

export type StreamConnection = 'connecting' | 'open' | 'reconnecting' | 'polling'

export interface HealthStatus {
  reachable: boolean
  /** Whether the AI model is currently answering; null when the backend doesn't say. */
  llmAvailable: boolean | null
}

export interface StreamHandlers {
  onEvent: (event: DiagnosisEvent) => void
  onConnectionChange?: (state: StreamConnection, attempt?: number) => void
}

/** Everything the UI needs from the backend — implemented by the live API and the mock. */
export interface DiagnosisBackend {
  readonly mode: 'live' | 'mock'
  health(signal?: AbortSignal): Promise<HealthStatus>
  createDiagnosis(req: DiagnosisRequest, signal?: AbortSignal): Promise<CreateDiagnosisResponse>
  /** Streams typed events; resolves after `done`, rejects on unrecoverable errors. */
  streamEvents(jobId: string, handlers: StreamHandlers, signal: AbortSignal): Promise<void>
  getDiagnosis(jobId: string, signal?: AbortSignal): Promise<JobSnapshot>
  decide(jobId: string, decision: Decision, payload: DecisionPayload): Promise<void>
  submitFeedback(jobId: string, payload: FeedbackPayload): Promise<void>
}

export const backend: DiagnosisBackend = config.useMock ? createMockBackend() : createLiveBackend(config.apiBaseUrl)
