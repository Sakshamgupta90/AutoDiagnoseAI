<script setup lang="ts">
import { AlertTriangle, BookPlus, CheckCircle2, CloudOff, Hourglass, Lock, PencilLine, PlugZap, RotateCcw, ShieldAlert, ShieldCheck, Square, XCircle } from 'lucide-vue-next'
import { computed } from 'vue'
import BrandMark from '@/components/BrandMark.vue'
import ConfidenceMeter from '@/components/ConfidenceMeter.vue'
import DecisionPanel from '@/components/DecisionPanel.vue'
import DiagnosisReport from '@/components/DiagnosisReport.vue'
import FeedbackForm from '@/components/FeedbackForm.vue'
import ReasoningTrace from '@/components/ReasoningTrace.vue'
import { formatTime, relativeTime } from '@/lib/format'
import { isInFlight, useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'
import type { AssistantMessage, ChatMessage } from '@/types/chat'
import type { Decision, FeedbackPayload } from '@/types/diagnosis'

const props = defineProps<{ message: AssistantMessage; conversationId: string; request?: ChatMessage }>()
const chat = useChatStore()
const ui = useUiStore()

const m = computed(() => props.message)
const live = computed(() => isInFlight(m.value.status))
const d = computed(() => m.value.diagnosis)
const needsSenior = computed(() => !!d.value?.escalation_required)
// Safety-critical plans are hidden until a senior approves (M3). Low-confidence answers stay visible —
// the tests to run are the answer — but still need a senior's review.
const hardBlock = computed(() => needsSenior.value && d.value?.escalation_type !== 'low_confidence')
const gated = computed(() => hardBlock.value && m.value.decision?.decision !== 'approved')
const photoCount = computed(() => (props.request?.role === 'user' ? props.request.attachments.length : 0))

const statusLine = computed(() => {
  switch (m.value.status) {
    case 'submitting':
      return photoCount.value ? `Uploading ${photoCount.value} photo${photoCount.value > 1 ? 's' : ''}…` : 'Sending to the diagnosis agent…'
    case 'reconnecting':
      return `Connection dropped — reconnecting${m.value.reconnectAttempt ? ` (attempt ${m.value.reconnectAttempt})` : ''}…`
    case 'polling':
      return 'Live updates unavailable — checking for the result…'
    default:
      return ''
  }
})

function decide(decision: Decision, technicianId: string, notes: string) {
  return chat.decide(props.conversationId, m.value.id, decision, { technician_id: technicianId, notes: notes || undefined }, needsSenior.value)
}
function feedback(payload: FeedbackPayload) {
  return chat.submitFeedback(props.conversationId, m.value.id, payload)
}
function editAndResend() {
  const r = props.request
  if (r?.role !== 'user') return
  ui.setDraft({ text: r.text, vehicle: r.vehicle })
}
</script>

<template>
  <div class="flex gap-3">
    <div class="hidden shrink-0 pt-0.5 sm:block"><BrandMark :size="28" /></div>

    <div class="min-w-0 flex-1 space-y-3">
      <!-- Header -->
      <div class="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1">
        <div class="flex items-center gap-2">
          <BrandMark :size="22" class="sm:hidden" />
          <span class="text-sm font-semibold">AutoDiagnose</span>
          <span class="rounded-full border border-line bg-surface-2 px-1.5 py-px text-[10px] font-medium text-muted">Agent</span>
          <span v-if="m.jobId" class="hidden font-mono text-[11px] text-muted sm:inline">{{ m.jobId }}</span>
        </div>
        <ConfidenceMeter
          v-if="m.steps.length || m.confidence !== null"
          class="ml-auto"
          :value="m.confidence"
          :history="m.confidenceHistory"
          :live="live"
        />
      </div>

      <!-- Connecting / uploading -->
      <div v-if="statusLine" class="flex items-center gap-2 text-sm" :class="m.status === 'submitting' ? 'text-fg-soft' : 'text-warn'" role="status">
        <PlugZap v-if="m.status !== 'submitting'" class="size-4" />
        <span v-else class="flex gap-1" aria-hidden="true">
          <span v-for="i in 3" :key="i" class="size-1.5 animate-pulse-dot rounded-full bg-brand" :style="{ animationDelay: `${i * 150}ms` }" />
        </span>
        {{ statusLine }}
      </div>

      <!-- Operational notices -->
      <div
        v-for="n in m.notices"
        :key="n.kind"
        class="flex gap-2.5 rounded-xl border px-3 py-2.5 text-sm"
        :class="n.kind === 'cloud_unreachable' ? 'border-warn/30 bg-warn/10' : n.kind === 'knowledge_gap' ? 'border-brand/25 bg-brand-soft' : 'border-info/25 bg-info/10'"
        role="status"
      >
        <CloudOff v-if="n.kind === 'cloud_unreachable'" class="mt-0.5 size-4 shrink-0 text-warn" />
        <BookPlus v-else-if="n.kind === 'knowledge_gap'" class="mt-0.5 size-4 shrink-0 text-brand" />
        <Hourglass v-else class="mt-0.5 size-4 shrink-0 text-info" />
        <div>
          <p class="font-medium">{{ n.kind === 'cloud_unreachable' ? 'Cloud unreachable — offline fallback' : n.kind === 'budget_exhausted' ? 'Reasoning budget reached' : n.kind === 'knowledge_gap' ? 'New case — answered from general knowledge' : 'Note' }}</p>
          <p class="text-fg-soft">{{ n.message }}</p>
        </div>
      </div>

      <!-- Live escalation, before the final answer -->
      <div v-if="m.escalation && !d" class="flex animate-fade-up gap-2.5 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2.5 text-sm" role="alert">
        <ShieldAlert class="mt-0.5 size-4 shrink-0 text-warn" />
        <p><span class="font-medium capitalize">{{ m.escalation.category }}</span> · {{ m.escalation.reason }}</p>
      </div>

      <ReasoningTrace
        v-if="m.steps.length || m.status === 'streaming'"
        :steps="m.steps"
        :live="live"
        :started-at="m.startedAt"
        :finished-at="m.finishedAt"
      />

      <!-- Failure states -->
      <div v-if="m.status === 'error'" class="rounded-xl border border-danger/30 bg-danger/5 p-3.5" role="alert">
        <div class="flex gap-2.5">
          <AlertTriangle class="mt-0.5 size-4 shrink-0 text-danger" />
          <div class="min-w-0">
            <p class="text-sm font-medium">The diagnosis didn’t complete</p>
            <p class="mt-0.5 text-sm text-fg-soft">{{ m.error?.message }}</p>
          </div>
        </div>
        <div class="mt-3 flex flex-wrap gap-2 pl-6.5">
          <button v-if="m.error?.retryable !== false" class="btn-primary py-1.5 text-xs" :disabled="chat.activeBusy" @click="chat.retry(conversationId, m.id)">
            <RotateCcw class="size-3.5" /> Try again
          </button>
          <button class="btn-secondary py-1.5 text-xs" @click="editAndResend"><PencilLine class="size-3.5" /> Edit & resend</button>
        </div>
      </div>

      <div v-else-if="m.status === 'cancelled'" class="flex flex-wrap items-center gap-3 text-sm text-muted">
        <span class="flex items-center gap-1.5"><Square class="size-3.5" /> Stopped.</span>
        <button class="btn-ghost px-2 py-1 text-xs" :disabled="chat.activeBusy" @click="chat.retry(conversationId, m.id)"><RotateCcw class="size-3.5" /> Run again</button>
      </div>

      <div v-else-if="m.status === 'interrupted'" class="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-3 text-sm">
        <PlugZap class="size-4 text-warn" />
        <span class="flex-1 text-fg-soft">This diagnosis was still running when the page closed.</span>
        <button class="btn-primary py-1.5 text-xs" :disabled="chat.activeBusy" @click="chat.resume(conversationId, m.id)">Reconnect</button>
      </div>

      <!-- Final answer -->
      <template v-if="d && m.status === 'complete'">
        <template v-if="gated">
          <div v-if="m.decision?.decision === 'rejected'" class="flex gap-2.5 rounded-xl border border-line bg-surface p-3.5 text-sm">
            <XCircle class="mt-0.5 size-4 shrink-0 text-danger" />
            <div>
              <p class="font-medium">Plan rejected by senior technician {{ m.decision.by }}</p>
              <p v-if="m.decision.notes" class="mt-0.5 text-fg-soft">“{{ m.decision.notes }}”</p>
              <button class="btn-secondary mt-3 py-1.5 text-xs" @click="editAndResend"><PencilLine class="size-3.5" /> Add details & re-run</button>
            </div>
          </div>
          <template v-else>
            <!-- Placeholder only: the real plan is never rendered until approval. -->
            <div class="relative overflow-hidden rounded-xl border border-line bg-surface p-4" aria-hidden="true">
              <div class="space-y-2.5 blur-[3px] select-none">
                <div class="skeleton h-3.5 w-3/4" />
                <div class="skeleton h-3.5 w-2/3" />
                <div class="skeleton h-3.5 w-1/2" />
                <div class="skeleton h-3.5 w-3/5" />
              </div>
              <div class="absolute inset-0 grid place-items-center bg-surface/40">
                <span class="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium shadow-sm">
                  <Lock class="size-3.5 text-warn" /> Repair plan locked until sign-off
                </span>
              </div>
            </div>
            <DecisionPanel senior :reason="m.escalation?.reason" :category="m.escalation?.category" :submit="decide" />
          </template>
        </template>

        <template v-else>
          <div v-if="m.decision?.senior" class="flex items-center gap-2 text-xs text-ok">
            <ShieldCheck class="size-4" /> Approved by senior technician {{ m.decision.by }} · {{ relativeTime(m.decision.at) }}
          </div>
          <DiagnosisReport :diagnosis="d" />

          <DecisionPanel
            v-if="!m.decision"
            :senior="needsSenior"
            :blocking="false"
            :reason="needsSenior ? m.escalation?.reason : undefined"
            :category="needsSenior ? m.escalation?.category : undefined"
            :submit="decide"
          />

          <div v-else-if="m.decision.decision === 'rejected'" class="flex gap-2.5 rounded-xl border border-line bg-surface p-3.5 text-sm">
            <XCircle class="mt-0.5 size-4 shrink-0 text-danger" />
            <div>
              <p class="font-medium">Rejected by {{ m.decision.by }}</p>
              <p v-if="m.decision.notes" class="mt-0.5 text-fg-soft">“{{ m.decision.notes }}”</p>
              <button class="btn-secondary mt-3 py-1.5 text-xs" @click="editAndResend"><PencilLine class="size-3.5" /> Add details & re-run</button>
            </div>
          </div>

          <FeedbackForm v-else-if="!m.feedback" :causes="d.ranked_causes" :submit="feedback" />

          <div v-else class="flex gap-2.5 rounded-xl border border-ok/30 bg-ok/5 p-3.5 text-sm">
            <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-ok" />
            <div>
              <p class="font-medium">Job closed · {{ formatTime(m.feedback.at) }}</p>
              <p class="mt-0.5 text-fg-soft">
                <span class="font-medium text-fg">{{ m.feedback.confirmed_cause }}</span> — {{ m.feedback.confirmed_fix }}
              </p>
              <p class="mt-1 text-xs text-muted">Added to the workshop knowledge base.</p>
            </div>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>
