<script setup lang="ts">
import { computed } from 'vue'
import { confidenceBand, formatPercent } from '@/lib/format'

const props = defineProps<{ value: number | null; history?: number[]; live?: boolean }>()

const band = computed(() => (props.value === null ? null : confidenceBand(props.value)))
const tone = computed(
  () =>
    ({ low: 'text-danger', medium: 'text-warn', high: 'text-ok' } as const)[band.value ?? 'low'] ??
    'text-muted',
)
const bar = computed(() => ({ low: 'bg-danger', medium: 'bg-warn', high: 'bg-ok' } as const)[band.value ?? 'low'])
const label = computed(() => ({ low: 'Low', medium: 'Moderate', high: 'High' } as const)[band.value ?? 'low'])

/** Tiny sparkline of confidence after each reasoning turn. */
const points = computed(() => {
  const h = props.history ?? []
  if (h.length < 2) return ''
  return h.map((v, i) => `${(i / (h.length - 1)) * 40},${14 - v * 12}`).join(' ')
})
</script>

<template>
  <div class="flex items-center gap-2" role="meter" :aria-valuenow="value === null ? undefined : Math.round(value * 100)" aria-valuemin="0" aria-valuemax="100" aria-label="Diagnosis confidence">
    <svg v-if="points" width="40" height="16" viewBox="0 0 40 16" class="hidden sm:block" aria-hidden="true">
      <polyline :points="points" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" :class="tone" />
    </svg>
    <div class="w-20">
      <div class="flex items-baseline justify-between text-[11px]">
        <span class="text-muted">Confidence</span>
      </div>
      <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div
          v-if="value !== null"
          class="h-full rounded-full transition-[width] duration-700 ease-out"
          :class="bar"
          :style="{ width: `${Math.max(4, value * 100)}%` }"
        />
        <div v-else-if="live" class="skeleton h-full w-full" />
      </div>
    </div>
    <div class="min-w-11 text-right">
      <div class="text-sm font-semibold tabular-nums" :class="value === null ? 'text-muted' : tone">{{ value === null ? '—' : formatPercent(value) }}</div>
      <div v-if="value !== null" class="text-[10px] leading-none text-muted">{{ label }}</div>
    </div>
  </div>
</template>
