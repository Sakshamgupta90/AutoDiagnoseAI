/**
 * In-browser mock of the FastAPI orchestrator. It follows the frozen
 * contract exactly (POST -> job_id, typed SSE events, approval, feedback) so
 * the UI can be built and demoed before the backend is live.
 *
 * Demo triggers in the symptom text:
 *   #error   -> job creation fails (network error handling)
 *   #drop    -> stream drops mid-way and reconnects
 *   #offline -> Bedrock unreachable, local keyword fallback + banner
 */
import type {
  Diagnosis,
  DiagnosisEvent,
  DiagnosisRequest,
  JobSnapshot,
  StepEventData,
} from '@/types/diagnosis'
import type { DiagnosisBackend } from './backend'
import { ApiError } from './errors'

type Timeline = Array<{ delay: number; event: DiagnosisEvent }>

interface MockJob {
  snapshot: JobSnapshot
  timeline: Timeline
  dropAt?: number
  cursor: number
}

const jobs = new Map<string, MockJob>()

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason)
    const t = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => (clearTimeout(t), reject(signal.reason)), { once: true })
  })
}

const jitter = (ms: number) => Math.round(ms * (0.75 + Math.random() * 0.5))

function vehicleLabel(req: DiagnosisRequest) {
  if (req.make || req.model) return [req.make, req.model].filter(Boolean).join(' ')
  if (req.vin) return 'Toyota Corolla Altis 1.6 (2018)'
  return 'Unknown vehicle'
}

function step(step_no: number, tool_used: string, key_inputs: Record<string, unknown>, turn: number): DiagnosisEvent {
  return { type: 'step', data: { step_no, tool_used, key_inputs, turn } satisfies StepEventData }
}
const evidence = (source: string, chunk_id: string, snippet_ref: string): DiagnosisEvent => ({
  type: 'evidence',
  data: { source, chunk_id, snippet_ref },
})
const confidence = (value: number): DiagnosisEvent => ({ type: 'confidence', data: { value } })

type Scenario = 'misfire' | 'brakes' | 'overheating' | 'electrical' | 'unclear'

function pickScenario(req: DiagnosisRequest): Scenario {
  const text = `${req.symptom_text} ${req.dtc_codes.join(' ')}`.toLowerCase()
  if (/brake|squeal|grind|pedal|abs|c00|stopping/.test(text)) return 'brakes'
  if (/overheat|coolant|temperature|temp gauge|steam|radiator|p0217|p0128/.test(text)) return 'overheating'
  if (/misfire|rough idle|p030|shak|hesitat|stutter|ignition coil/.test(text)) return 'misfire'
  if (/battery|crank|won'?t start|no start|alternator|dim|electrical|p0562|charging/.test(text)) return 'electrical'
  return 'unclear'
}

function buildTimeline(req: DiagnosisRequest, jobId: string): { timeline: Timeline; diagnosis: Diagnosis } {
  const scenario = pickScenario(req)
  const offline = /#offline/i.test(req.symptom_text)
  const vehicle = vehicleLabel(req)
  const dtc = req.dtc_codes
  const t: Timeline = []
  let n = 0
  const push = (delay: number, event: DiagnosisEvent) => t.push({ delay: jitter(delay), event })

  if (offline) {
    push(500, {
      type: 'notice',
      data: {
        kind: 'cloud_unreachable',
        message: 'AWS Bedrock is unreachable. Using the local keyword search over the same knowledge base — results are less precise.',
      },
    })
  }

  // Turn 1 — identify the vehicle and pull history.
  if (req.vin || req.make) {
    push(700, step(++n, 'vin_decode', req.vin ? { vin: req.vin } : { make: req.make, model: req.model }, 1))
    push(900, evidence('NHTSA vPIC', 'vin:decoded', `${vehicle} · 1.6L 4-cyl petrol · FWD`))
  }
  if (req.photos.length && !offline) {
    push(900, step(++n, 'photo_analysis', { photos: req.photos.length, model: 'claude-sonnet-4.5' }, 1))
  }
  push(800, step(++n, 'sqlite_history', { vin: req.vin || '—', lookback: '24 months' }, 1))

  let diagnosis: Diagnosis
  switch (scenario) {
    case 'misfire': {
      const code = dtc.find((c) => c.startsWith('P030')) ?? 'P0301'
      const cyl = code.at(-1) === '0' ? 'multiple cylinders' : `cylinder ${code.at(-1)}`
      push(900, evidence('Service history', 'job-2025-11-04', 'Spark plugs replaced 41,000 km ago; coils never replaced.'))
      push(400, confidence(0.41))
      push(900, step(++n, 'qdrant_search', { query: 'misfire rough idle cold start', dtc: code, filter: 'make/model' }, 2))
      push(1000, evidence('Zenodo AFD', 'afd-0231', `${code}: misfire detected on ${cyl} — commonly ignition coil or plug.`))
      push(500, evidence('Flowchart · Electrical', 'fc-elec-b3', 'Swap coil to adjacent cylinder; if misfire follows, replace coil.'))
      push(400, confidence(0.68))
      push(900, step(++n, 'qdrant_search', { query: 'ignition coil failure symptoms', dtc: code, narrow: true }, 3))
      push(900, evidence('Zenodo AFD', 'afd-0417', 'Coil-on-plug failure worsens when cold or under load.'))
      push(400, confidence(0.84))
      diagnosis = {
        job_id: jobId,
        summary: `The ${code} misfire on ${cyl} most likely comes from a failing ignition coil. The plugs are recent, and the rough idle is worse when cold, which is typical of coil breakdown. Swap the coil to confirm before ordering parts.`,
        ranked_causes: [
          { cause: `Failing ignition coil (${cyl})`, confidence: 0.84, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0231' }, { source: 'Flowchart · Electrical', chunk_id: 'fc-elec-b3' }] },
          { cause: 'Worn or fouled spark plug', confidence: 0.52, evidence: [{ source: 'Service history', chunk_id: 'job-2025-11-04' }] },
          { cause: 'Clogged fuel injector', confidence: 0.23, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0417' }] },
        ],
        confirmation_tests: [
          `Swap the ${cyl} coil with an adjacent cylinder, clear codes and road-test — check whether the misfire follows the coil.`,
          'Inspect the spark plug for carbon fouling, oil or a cracked insulator; check the gap (0.8–0.9 mm).',
          'Check coil primary resistance (0.4–0.8 Ω) and the connector for corrosion.',
          'If the misfire stays on the same cylinder, run an injector balance test.',
        ],
        parts_estimate: [
          { part: 'Ignition coil (OEM)', est_cost: 145 },
          { part: 'Spark plug, iridium', est_cost: 28 },
        ],
        labour_estimate_hours: 0.8,
        safety_flags: [],
        escalation_required: false,
      }
      break
    }
    case 'brakes': {
      push(900, evidence('Service history', 'job-2026-02-18', 'Front pads at 3 mm noted in last service — replacement advised, declined by customer.'))
      push(400, confidence(0.55))
      push(900, step(++n, 'qdrant_search', { query: 'brake squeal grinding when stopping', category: 'brakes' }, 2))
      push(1000, evidence('Flowchart · Brakes', 'fc-brake-b1', 'Grinding under braking: inspect pad thickness and rotor scoring first.'))
      push(500, { type: 'escalation', data: { category: 'brakes', reason: 'Brake-system fault — plan requires senior technician sign-off before release.' } })
      push(600, confidence(0.79))
      diagnosis = {
        job_id: jobId,
        summary: 'Front pads have probably worn past the wear indicator, so the backing plate is now touching the rotor. This needs attention before the vehicle goes back on the road.',
        ranked_causes: [
          { cause: 'Front brake pads worn to backing plate', confidence: 0.79, evidence: [{ source: 'Service history', chunk_id: 'job-2026-02-18' }, { source: 'Flowchart · Brakes', chunk_id: 'fc-brake-b1' }] },
          { cause: 'Scored or warped front rotors', confidence: 0.61, evidence: [{ source: 'Flowchart · Brakes', chunk_id: 'fc-brake-b1' }] },
          { cause: 'Seized caliper slide pin', confidence: 0.27, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0112' }] },
        ],
        confirmation_tests: [
          'Remove the front wheels and measure pad thickness (service limit 2 mm).',
          'Measure rotor thickness and runout; look for deep scoring.',
          'Check the caliper slide pins move freely and the boots are intact.',
          'Road-test at low speed after repair and confirm there is no pull or pulsation.',
        ],
        parts_estimate: [
          { part: 'Front brake pad set', est_cost: 95 },
          { part: 'Front rotors (pair)', est_cost: 220 },
        ],
        labour_estimate_hours: 1.5,
        safety_flags: ['Brakes', 'Do not release vehicle until repaired'],
        escalation_required: true,
        escalation_type: 'safety',
      }
      break
    }
    case 'overheating': {
      push(900, evidence('Service history', 'job-2025-08-30', 'Coolant top-up recorded twice in 6 months.'))
      push(400, confidence(0.44))
      push(900, step(++n, 'qdrant_search', { query: 'engine overheating coolant loss', category: 'overheating', dtc: dtc[0] ?? null }, 2))
      push(1000, evidence('Flowchart · Overheating', 'fc-heat-b2', 'Coolant loss with no visible leak: pressure-test system and check head gasket.'))
      push(500, evidence('Zenodo AFD', 'afd-0078', 'Thermostat stuck closed: rapid temperature rise, upper hose hot, lower hose cold.'))
      push(400, confidence(0.72))
      diagnosis = {
        job_id: jobId,
        summary: 'The repeated coolant top-ups and overheating point to a leak in the cooling system, with a thermostat stuck closed as a close second. Pressure-test the system before anything else.',
        ranked_causes: [
          { cause: 'External coolant leak (hose / water pump)', confidence: 0.72, evidence: [{ source: 'Service history', chunk_id: 'job-2025-08-30' }, { source: 'Flowchart · Overheating', chunk_id: 'fc-heat-b2' }] },
          { cause: 'Thermostat stuck closed', confidence: 0.58, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0078' }] },
          { cause: 'Head gasket failure', confidence: 0.21, evidence: [{ source: 'Flowchart · Overheating', chunk_id: 'fc-heat-b2' }] },
        ],
        confirmation_tests: [
          'Pressure-test the cooling system at 1.1 bar for 10 minutes and check for drops.',
          'Warm the engine and compare upper and lower radiator hose temperatures.',
          'Check the radiator fan comes on at operating temperature.',
          'If no external leak, run a combustion gas (block) test on the coolant.',
        ],
        parts_estimate: [
          { part: 'Thermostat + gasket', est_cost: 65 },
          { part: 'Coolant (4 L)', est_cost: 38 },
        ],
        labour_estimate_hours: 1.2,
        safety_flags: ['Do not open the radiator cap while hot'],
        escalation_required: false,
      }
      break
    }
    case 'electrical': {
      push(900, evidence('Service history', 'job-2024-12-02', 'Battery installed Dec 2024 (22 months).'))
      push(400, confidence(0.47))
      push(900, step(++n, 'qdrant_search', { query: 'slow crank no start dim lights', category: 'electrical' }, 2))
      push(1000, evidence('Flowchart · Electrical', 'fc-elec-b1', 'Measure resting voltage; below 12.4 V charge and load-test before replacing.'))
      push(400, confidence(0.74))
      diagnosis = {
        job_id: jobId,
        summary: 'A slow crank with dim lights points to a weak battery or a charging fault. Load-test the battery and check the alternator output before replacing parts.',
        ranked_causes: [
          { cause: 'Weak / sulphated battery', confidence: 0.74, evidence: [{ source: 'Flowchart · Electrical', chunk_id: 'fc-elec-b1' }] },
          { cause: 'Alternator under-charging', confidence: 0.49, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0355' }] },
          { cause: 'Corroded battery terminals', confidence: 0.31, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0356' }] },
        ],
        confirmation_tests: [
          'Measure resting battery voltage (expect ≥ 12.6 V) and run a load test.',
          'With the engine running, check charging voltage at 2,000 rpm (13.8–14.7 V).',
          'Clean the terminals and check the earth strap for voltage drop.',
        ],
        parts_estimate: [{ part: 'Battery 55D23L', est_cost: 180 }],
        labour_estimate_hours: 0.5,
        safety_flags: [],
        escalation_required: false,
      }
      break
    }
    default: {
      push(900, evidence('Service history', 'none', 'No previous jobs found for this vehicle.'))
      push(400, confidence(0.22))
      push(900, step(++n, 'qdrant_search', { query: req.symptom_text.slice(0, 60) }, 2))
      push(1000, evidence('Zenodo AFD', 'afd-0009', 'Several loosely matching records — none specific enough.'))
      push(400, confidence(0.34))
      push(900, step(++n, 'qdrant_search', { query: 'general inspection checklist', narrow: true }, 3))
      push(700, { type: 'notice', data: { kind: 'budget_exhausted', message: 'Reasoning budget reached (3 turns). Returning the tests to run first rather than a guess.' } })
      push(400, confidence(0.34))
      diagnosis = {
        job_id: jobId,
        summary: 'There isn’t enough evidence to name a likely cause yet. Run the checks below and add any fault codes or photos. A description of when the symptom happens also helps.',
        ranked_causes: [
          { cause: 'Insufficient evidence — needs more information', confidence: 0.34, evidence: [{ source: 'Zenodo AFD', chunk_id: 'afd-0009' }] },
        ],
        confirmation_tests: [
          'Scan all modules for stored and pending fault codes (OBD-II).',
          'Record when the symptom occurs: cold/warm, speed, load, weather.',
          'Take photos of any visible leaks, damage or warning lights.',
        ],
        parts_estimate: [],
        labour_estimate_hours: 0.5,
        safety_flags: [],
        escalation_required: true,
        escalation_type: 'low_confidence',
        budget_exhausted: true,
      }
    }
  }

  if (offline) {
    // Keyword fallback is less precise: scale confidence down consistently.
    for (const item of t) if (item.event.type === 'confidence') item.event.data.value = Math.round(item.event.data.value * 0.8 * 100) / 100
    diagnosis = {
      ...diagnosis,
      fallback_mode: true,
      ranked_causes: diagnosis.ranked_causes.map((c) => ({ ...c, confidence: Math.round(c.confidence * 0.8 * 100) / 100 })),
    }
  }
  push(900, { type: 'done', data: diagnosis })
  return { timeline: t, diagnosis }
}

export function createMockBackend(): DiagnosisBackend {
  return {
    mode: 'mock',

    async health() {
      return navigator.onLine
    },

    async createDiagnosis(req, signal) {
      await sleep(req.photos.length ? 900 : 450, signal ?? new AbortController().signal)
      if (/#error/i.test(req.symptom_text))
        throw new ApiError('Can’t reach the diagnosis service. Check your connection and try again.', { code: 'network' })
      const job_id = `job_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
      const { timeline } = buildTimeline(req, job_id)
      const dropAt = /#drop/i.test(req.symptom_text) ? Math.floor(timeline.length / 2) : undefined
      jobs.set(job_id, { snapshot: { job_id, status: 'queued' }, timeline, dropAt, cursor: 0 })
      return { job_id, status: 'queued' }
    },

    async streamEvents(jobId, handlers, signal) {
      const job = jobs.get(jobId)
      if (!job) throw new ApiError('That diagnosis job could not be found. It may have expired.', { code: 'not_found', retryable: false })
      handlers.onConnectionChange?.('connecting', 0)
      await sleep(300, signal)
      handlers.onConnectionChange?.('open')
      job.snapshot.status = 'running'

      while (job.cursor < job.timeline.length) {
        if (job.dropAt !== undefined && job.cursor === job.dropAt) {
          job.dropAt = undefined
          handlers.onConnectionChange?.('reconnecting', 1)
          await sleep(2200, signal)
          handlers.onConnectionChange?.('open')
        }
        const { delay, event } = job.timeline[job.cursor]
        await sleep(delay, signal)
        job.cursor++
        handlers.onEvent(event)
        if (event.type === 'done') {
          job.snapshot = {
            job_id: jobId,
            status: event.data.escalation_required ? 'awaiting_approval' : 'running',
            diagnosis: event.data,
          }
        }
      }
    },

    async getDiagnosis(jobId) {
      const job = jobs.get(jobId)
      if (!job) throw new ApiError('That diagnosis job could not be found. It may have expired.', { code: 'not_found', retryable: false })
      return job.snapshot
    },

    async decide(jobId, decision) {
      await sleep(500, new AbortController().signal)
      const job = jobs.get(jobId)
      if (job) job.snapshot.status = decision === 'approve' ? 'approved' : 'rejected'
    },

    async submitFeedback(jobId) {
      await sleep(600, new AbortController().signal)
      const job = jobs.get(jobId)
      if (job) job.snapshot.status = 'closed'
    },
  }
}
