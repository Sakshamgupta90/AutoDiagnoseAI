/**
 * Types mirroring the interface contracts frozen on 18 Sep
 * (Refined Architecture, Section 6). Fields marked "extension" are optional
 * additions the UI understands but does not require from the backend.
 */

export type ToolName =
  | 'vin_decode'
  | 'qdrant_search'
  | 'sqlite_history'
  // Any other tool the orchestrator adds later still renders with a generic label.
  | (string & {})

export type JobStatus =
  | 'queued'
  | 'running'
  | 'awaiting_approval'
  | 'approved'
  | 'rejected'
  | 'closed'
  | 'failed'

/** POST /diagnoses (multipart/form-data) — Section 6.1 */
export interface DiagnosisRequest {
  vin?: string
  make?: string
  model?: string
  dtc_codes: string[]
  symptom_text: string
  photos: File[]
  /** extension: lets the backend group follow-up questions from one chat. */
  session_id?: string
}

/** 202 response of POST /diagnoses */
export interface CreateDiagnosisResponse {
  job_id: string
  status: JobStatus
}

export interface EvidenceRef {
  source: string
  chunk_id: string
}

export interface RankedCause {
  cause: string
  /** 0–1 */
  confidence: number
  evidence: EvidenceRef[]
}

export interface PartEstimate {
  part: string
  est_cost: number
}

/** Final diagnosis object — Section 6.1 (M11) */
export interface Diagnosis {
  job_id: string
  ranked_causes: RankedCause[]
  confirmation_tests: string[]
  parts_estimate: PartEstimate[]
  labour_estimate_hours: number
  safety_flags: string[]
  escalation_required: boolean
  /** extension: short plain-language summary for the technician. */
  summary?: string
  /** extension: true when the local keyword fallback produced this result. */
  fallback_mode?: boolean
  /** extension: true when the 3-turn / ~6-tool / 45s budget forced the answer. */
  budget_exhausted?: boolean
  /** extension: why escalation is required — only `safety` hides the plan until sign-off. */
  escalation_type?: 'safety' | 'low_confidence' | null
  /** extension: what the answer rests on. */
  answer_source?: 'knowledge_base' | 'general_knowledge' | 'mixed' | 'fallback'
}

/* ---------- SSE events — Section 6.2 ---------- */

export interface StepEventData {
  step_no: number
  tool_used: ToolName
  key_inputs: Record<string, unknown>
  /** extension: reasoning turn (1–3). */
  turn?: number
}

export interface EvidenceEventData {
  source: string
  chunk_id: string
  snippet_ref?: string
}

export interface ConfidenceEventData {
  value: number
}

export interface EscalationEventData {
  reason: string
  category: string
}

/** extension: operational notices such as the "Cloud Unreachable" fallback. */
export interface NoticeEventData {
  kind: 'cloud_unreachable' | 'budget_exhausted' | 'knowledge_gap' | 'info'
  message: string
}

/** extension: an orchestrator failure surfaced over the stream. */
export interface ErrorEventData {
  message: string
  code?: string
  retryable?: boolean
}

export type DiagnosisEvent =
  | { type: 'step'; data: StepEventData }
  | { type: 'evidence'; data: EvidenceEventData }
  | { type: 'confidence'; data: ConfidenceEventData }
  | { type: 'escalation'; data: EscalationEventData }
  | { type: 'notice'; data: NoticeEventData }
  | { type: 'error'; data: ErrorEventData }
  | { type: 'done'; data: Diagnosis }

/** GET /diagnoses/{id} */
export interface JobSnapshot {
  job_id: string
  status: JobStatus
  diagnosis?: Diagnosis | null
  error?: string | null
}

/** POST /diagnoses/{id}/approve | /reject */
export interface DecisionPayload {
  technician_id: string
  notes?: string
}

/** POST /diagnoses/{id}/feedback */
export interface FeedbackPayload {
  confirmed_cause: string
  confirmed_fix: string
  part_cost?: number
  labour_hours?: number
}

export type Decision = 'approve' | 'reject'
