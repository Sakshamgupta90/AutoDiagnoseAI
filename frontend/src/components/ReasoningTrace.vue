<script setup lang="ts">
import { Check, ChevronDown, FileText, Loader2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { config } from '@/config'
import { useNow } from '@/composables/useNow'
import { formatDuration, formatInputs } from '@/lib/format'
import { toolMeta } from '@/lib/tools'
import type { TraceStep } from '@/types/chat'

const props = defineProps<{
  steps: TraceStep[]
  live: boolean
  startedAt: number
  finishedAt?: number
}>()

const expanded = ref(props.live)
// Collapse the trace once the answer arrives; keep it open while streaming.
watch(
  () => props.live,
  (live) => (expanded.value = live),
)

const now = useNow(computed(() => props.live))
const elapsed = computed(() => (props.finishedAt ?? now.value) - props.startedAt)
const sourceCount = computed(() => props.steps.reduce((n, s) => n + s.evidence.length, 0))
const turn = computed(() => Math.max(1, ...props.steps.map((s) => s.turn ?? 1)))
const budgetPct = computed(() => Math.min(100, (elapsed.value / (config.budget.seconds * 1000)) * 100))

const summary = computed(() => {
  const steps = `${props.steps.length} step${props.steps.length === 1 ? '' : 's'}`
  const sources = `${sourceCount.value} source${sourceCount.value === 1 ? '' : 's'}`
  return `Reasoned in ${steps} · ${sources} · ${formatDuration(elapsed.value)}`
})

function stepDuration(s: TraceStep) {
  return formatDuration((s.finishedAt ?? now.value) - s.startedAt)
}
</script>

<template>
  <section class="rounded-2xl border border-line bg-surface/70 shadow-xs backdrop-blur" aria-label="Agent reasoning trace">
    <button
      class="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <Loader2 v-if="live" class="size-4 shrink-0 animate-spin text-brand" />
      <Check v-else class="size-4 shrink-0 text-ok" />
      <span class="min-w-0 flex-1 truncate font-medium" :class="live ? 'text-fg' : 'text-fg-soft'">
        <template v-if="live">{{ steps.length ? toolMeta(steps.at(-1)!.tool_used).running + '…' : 'Planning the diagnosis…' }}</template>
        <template v-else>{{ summary }}</template>
      </span>
      <span v-if="live" class="hidden shrink-0 font-mono text-xs text-muted tabular-nums sm:inline">
        Turn {{ turn }}/{{ config.budget.turns }} · {{ steps.length }}/{{ config.budget.toolCalls }} tools · {{ formatDuration(elapsed) }}
      </span>
      <ChevronDown class="size-4 shrink-0 text-muted transition-transform" :class="expanded && 'rotate-180'" />
    </button>

    <div v-if="live" class="mx-3 -mt-1 mb-2 h-0.5 overflow-hidden rounded-full bg-surface-3" aria-hidden="true" :title="`Time budget: ${config.budget.seconds}s`">
      <div class="h-full bg-brand/60 transition-[width] duration-300" :style="{ width: `${budgetPct}%` }" />
    </div>

    <ol v-show="expanded" class="relative space-y-3 px-3 pt-1 pb-3" aria-live="polite">
      <li v-if="!steps.length" class="flex items-center gap-3 pl-0.5">
        <span class="size-6 shrink-0 skeleton rounded-full" />
        <span class="skeleton h-3 w-48" />
      </li>
      <li v-for="(s, i) in steps" :key="s.step_no" class="relative flex gap-3">
        <span v-if="i < steps.length - 1" class="absolute top-7 bottom-[-12px] left-3 w-px bg-line" aria-hidden="true" />
        <span
          class="relative z-10 grid size-6 shrink-0 place-items-center rounded-full border"
          :class="s.status === 'running' ? 'border-brand/40 bg-brand-soft text-brand' : 'border-line bg-surface text-fg-soft'"
        >
          <component :is="toolMeta(s.tool_used).icon" class="size-3.5" />
        </span>
        <div class="min-w-0 flex-1 pt-0.5">
          <div class="flex items-center gap-2 text-sm">
            <span :class="s.status === 'running' ? 'font-medium text-fg' : 'text-fg-soft'">
              {{ s.status === 'running' ? toolMeta(s.tool_used).running : toolMeta(s.tool_used).label }}
            </span>
            <Loader2 v-if="s.status === 'running'" class="size-3 animate-spin text-brand" />
            <span class="ml-auto shrink-0 font-mono text-[11px] text-muted tabular-nums">{{ stepDuration(s) }}</span>
          </div>
          <div v-if="Object.keys(s.key_inputs).length" class="mt-1 flex flex-wrap gap-1">
            <span v-for="[k, v] in formatInputs(s.key_inputs)" :key="k" class="chip max-w-full font-mono text-[11px]">
              <span class="text-muted">{{ k }}:</span><span class="truncate">{{ v }}</span>
            </span>
          </div>
          <ul v-if="s.evidence.length" class="mt-2 space-y-1.5">
            <li
              v-for="e in s.evidence"
              :key="e.source + e.chunk_id"
              class="flex animate-fade-up gap-2 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs"
            >
              <FileText class="mt-px size-3.5 shrink-0 text-info" />
              <div class="min-w-0">
                <div class="font-medium text-fg-soft">
                  {{ e.source }} <span class="font-mono font-normal text-muted">· {{ e.chunk_id }}</span>
                </div>
                <p v-if="e.snippet_ref" class="mt-0.5 text-muted">{{ e.snippet_ref }}</p>
              </div>
            </li>
          </ul>
        </div>
      </li>
    </ol>
  </section>
</template>
