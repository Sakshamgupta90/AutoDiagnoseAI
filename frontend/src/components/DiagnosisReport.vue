<script setup lang="ts">
import { AlertOctagon, CircleHelp, ClipboardCheck, Copy, FileText, Package, Printer, Wrench } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { config } from '@/config'
import { confidenceBand, formatCurrency, formatPercent } from '@/lib/format'
import { useToastStore } from '@/stores/toast'
import type { Diagnosis } from '@/types/diagnosis'

const props = defineProps<{ diagnosis: Diagnosis }>()
const toast = useToastStore()

const d = computed(() => props.diagnosis)
const top = computed(() => d.value.ranked_causes[0])
const lowConfidence = computed(() => !top.value || top.value.confidence < config.confidenceThreshold)
const partsTotal = computed(() => d.value.parts_estimate.reduce((n, p) => n + (Number(p.est_cost) || 0), 0))
const checked = ref<boolean[]>([])

const sourceLabel = computed(() => {
  switch (d.value.answer_source) {
    case 'knowledge_base':
      return { text: 'Grounded in the workshop knowledge base', dot: 'bg-ok' }
    case 'mixed':
      return { text: 'Knowledge base + general automotive knowledge', dot: 'bg-info' }
    case 'general_knowledge':
      return { text: 'General knowledge — unverified until a technician confirms the fix', dot: 'bg-warn' }
    case 'fallback':
      return { text: 'Offline fallback — local knowledge base only', dot: 'bg-warn' }
    default:
      return null
  }
})

const barTone = { low: 'bg-danger', medium: 'bg-warn', high: 'bg-ok' } as const
const textTone = { low: 'text-danger', medium: 'text-warn', high: 'text-ok' } as const

function asText(): string {
  const lines = [
    `AutoDiagnose AI — job ${d.value.job_id}`,
    '',
    d.value.summary ?? '',
    '',
    'Likely causes:',
    ...d.value.ranked_causes.map((c, i) => `  ${i + 1}. ${c.cause} (${formatPercent(c.confidence)}) — ${c.evidence.map((e) => `${e.source} ${e.chunk_id}`).join('; ')}`),
    '',
    'Confirmation tests:',
    ...d.value.confirmation_tests.map((t, i) => `  ${i + 1}. ${t}`),
    '',
    'Estimate:',
    ...d.value.parts_estimate.map((p) => `  ${p.part}: ${formatCurrency(p.est_cost)}`),
    `  Labour: ${d.value.labour_estimate_hours} h`,
  ]
  if (d.value.safety_flags.length) lines.push('', `Safety: ${d.value.safety_flags.join(', ')}`)
  return lines.filter((l, i, a) => !(l === '' && a[i - 1] === '')).join('\n')
}

const print = () => window.print()

async function copy() {
  try {
    await navigator.clipboard.writeText(asText())
    toast.success('Report copied')
  } catch {
    toast.error('Couldn’t copy', 'Clipboard access was blocked by the browser.')
  }
}
</script>

<template>
  <article class="space-y-4" aria-label="Diagnosis report">
    <!-- Headline -->
    <div
      v-if="lowConfidence"
      class="flex gap-3 rounded-xl border border-warn/30 bg-warn/10 p-3 text-sm"
      role="note"
    >
      <CircleHelp class="mt-0.5 size-5 shrink-0 text-warn" />
      <div>
        <p class="font-semibold text-fg">Insufficient evidence — run these tests first</p>
        <p class="mt-0.5 text-fg-soft">Confidence is below {{ formatPercent(config.confidenceThreshold) }}, so the agent isn’t naming a cause yet. A senior technician should review this.</p>
      </div>
    </div>

    <p v-if="d.summary" class="text-[15px] leading-relaxed text-pretty text-fg">{{ d.summary }}</p>

    <p v-if="sourceLabel" class="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs text-fg-soft">
      <span class="size-1.5 rounded-full" :class="sourceLabel.dot" /> {{ sourceLabel.text }}
    </p>

    <div v-if="d.safety_flags.length" class="flex flex-wrap items-center gap-1.5">
      <span v-for="f in d.safety_flags" :key="f" class="inline-flex items-center gap-1 rounded-md bg-danger/10 px-2 py-1 text-xs font-medium text-danger">
        <AlertOctagon class="size-3.5" /> {{ f }}
      </span>
    </div>

    <!-- Ranked causes -->
    <section class="card overflow-hidden">
      <h3 class="flex items-center gap-2 px-4 pt-3.5 pb-1.5 text-sm font-semibold">
        <Wrench class="size-4 text-brand" /> Likely causes
      </h3>
      <ol class="divide-y divide-line/70">
        <li v-for="(c, i) in d.ranked_causes" :key="c.cause" class="px-4 py-3">
          <div class="flex items-start gap-3">
            <span
              class="grid size-6 shrink-0 place-items-center rounded-full text-xs font-semibold"
              :class="i === 0 ? 'bg-brand-gradient text-white shadow-sm shadow-indigo-500/30' : 'bg-surface-3 text-fg-soft'"
            >{{ i + 1 }}</span>
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-3">
                <p class="text-sm" :class="i === 0 ? 'font-semibold' : 'font-medium text-fg-soft'">{{ c.cause }}</p>
                <span class="shrink-0 text-sm font-semibold tabular-nums" :class="textTone[confidenceBand(c.confidence)]">{{ formatPercent(c.confidence) }}</span>
              </div>
              <div class="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
                <div class="h-full rounded-full" :class="barTone[confidenceBand(c.confidence)]" :style="{ width: `${c.confidence * 100}%` }" />
              </div>
              <div v-if="c.evidence.length" class="mt-2 flex flex-wrap gap-1">
                <span v-for="e in c.evidence" :key="e.source + e.chunk_id" class="chip text-[11px]" :title="`${e.source} · ${e.chunk_id}`">
                  <FileText class="size-3 text-info" /> {{ e.source }} <span class="font-mono text-muted">{{ e.chunk_id }}</span>
                </span>
              </div>
            </div>
          </div>
        </li>
      </ol>
    </section>

    <div class="grid gap-4 md:grid-cols-5">
      <!-- Tests -->
      <section v-if="d.confirmation_tests.length" class="card md:col-span-3">
        <h3 class="flex items-center gap-2 px-4 pt-3.5 pb-1.5 text-sm font-semibold">
          <ClipboardCheck class="size-4 text-brand" /> Confirmation tests
          <span class="ml-auto text-xs font-normal text-muted">{{ checked.filter(Boolean).length }}/{{ d.confirmation_tests.length }} done</span>
        </h3>
        <ol class="space-y-1 p-2">
          <li v-for="(t, i) in d.confirmation_tests" :key="i">
            <label class="flex cursor-pointer gap-3 rounded-lg px-2 py-2 text-sm hover:bg-surface-2">
              <input v-model="checked[i]" type="checkbox" class="mt-0.5 size-4 shrink-0 accent-[var(--brand)]" />
              <span :class="checked[i] ? 'text-muted line-through' : 'text-fg-soft'">{{ t }}</span>
            </label>
          </li>
        </ol>
      </section>

      <!-- Estimate -->
      <section class="card md:col-span-2" :class="!d.confirmation_tests.length && 'md:col-span-5'">
        <h3 class="flex items-center gap-2 px-4 pt-3.5 pb-1.5 text-sm font-semibold">
          <Package class="size-4 text-brand" /> Estimate
        </h3>
        <dl class="space-y-2 px-4 py-3 text-sm">
          <div v-for="p in d.parts_estimate" :key="p.part" class="flex justify-between gap-3">
            <dt class="text-fg-soft">{{ p.part }}</dt>
            <dd class="shrink-0 tabular-nums">{{ formatCurrency(p.est_cost) }}</dd>
          </div>
          <p v-if="!d.parts_estimate.length" class="text-muted">No parts estimated yet.</p>
          <div class="flex justify-between gap-3">
            <dt class="text-fg-soft">Labour</dt>
            <dd class="shrink-0 tabular-nums">{{ d.labour_estimate_hours }} h</dd>
          </div>
          <div v-if="d.parts_estimate.length" class="flex justify-between gap-3 border-t border-line pt-2 font-semibold">
            <dt>Parts total</dt>
            <dd class="tabular-nums">{{ formatCurrency(partsTotal) }}</dd>
          </div>
        </dl>
        <p class="px-4 pb-3 text-[11px] text-muted">Indicative only — confirm prices with your parts supplier.</p>
      </section>
    </div>

    <div class="no-print flex flex-wrap gap-2">
      <button class="btn-secondary py-1.5 text-xs" @click="copy"><Copy class="size-3.5" /> Copy report</button>
      <button class="btn-secondary py-1.5 text-xs" @click="print"><Printer class="size-3.5" /> Print</button>
    </div>
  </article>
</template>
