<script setup lang="ts">
import { Car } from 'lucide-vue-next'
import { computed } from 'vue'
import { formatTime } from '@/lib/format'
import { useUiStore } from '@/stores/ui'
import type { UserMessage } from '@/types/chat'

const props = defineProps<{ message: UserMessage }>()
const ui = useUiStore()

const v = computed(() => props.message.vehicle)
const vehicleName = computed(() => [v.value.make, v.value.model].filter(Boolean).join(' '))
const hasVehicle = computed(() => !!(v.value.vin || vehicleName.value || v.value.dtc_codes.length))
</script>

<template>
  <div class="flex flex-col items-end gap-2">
    <div v-if="message.attachments.length" class="flex max-w-[88%] flex-wrap justify-end gap-2">
      <button
        v-for="a in message.attachments"
        :key="a.id"
        class="overflow-hidden rounded-2xl border border-line shadow-sm transition hover:scale-[1.02] hover:shadow-md"
        :aria-label="`View photo ${a.name}`"
        @click="ui.openLightbox(a)"
      >
        <img :src="a.thumbUrl" :alt="a.name" class="size-24 object-cover sm:size-28" loading="lazy" />
      </button>
    </div>

    <div class="max-w-[88%] rounded-3xl rounded-br-lg border border-line bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed text-fg shadow-xs sm:max-w-[80%]">
      <div v-if="hasVehicle" class="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs text-fg-soft">
        <Car class="size-3.5 text-brand" />
        <span v-if="vehicleName" class="font-medium">{{ vehicleName }}</span>
        <span v-if="v.vin" class="font-mono">{{ v.vin }}</span>
        <span v-for="c in v.dtc_codes" :key="c" class="rounded bg-brand/15 px-1.5 py-px font-mono font-medium text-brand-strong">{{ c }}</span>
      </div>
      <p class="whitespace-pre-wrap break-words">{{ message.text }}</p>
    </div>
    <time class="px-1 text-[11px] text-muted" :datetime="new Date(message.createdAt).toISOString()">{{ formatTime(message.createdAt) }}</time>
  </div>
</template>
