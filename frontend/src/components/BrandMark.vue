<script setup lang="ts">
import { useId } from 'vue'

defineProps<{ size?: number }>()
const gid = `bm-${useId()}`
</script>

<template>
  <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 32 32" aria-hidden="true" class="shrink-0">
    <defs>
      <linearGradient :id="gid" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#6366f1" />
        <stop offset="1" stop-color="#a855f7" />
      </linearGradient>
    </defs>
    <rect width="32" height="32" rx="9" :fill="`url(#${gid})`" />
    <rect x="0.5" y="0.5" width="31" height="31" rx="8.5" fill="none" stroke="white" stroke-opacity="0.18" />
    <path d="M8 20.5a8 8 0 1 1 16 0" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round" />
    <path d="M16 20.5l4.5-5.5" stroke="white" stroke-width="2.4" stroke-linecap="round" />
    <circle cx="16" cy="20.5" r="2.1" fill="white" />
  </svg>
</template>
