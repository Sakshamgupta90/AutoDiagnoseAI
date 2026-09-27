<script setup lang="ts">
import { Menu, Monitor, Moon, SquarePen, Sun } from 'lucide-vue-next'
import { computed } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useChatStore } from '@/stores/chat'
import { useConnectionStore } from '@/stores/connection'
import { useUiStore } from '@/stores/ui'

const chat = useChatStore()
const ui = useUiStore()
const conn = useConnectionStore()
const theme = useTheme()

const vehicle = computed(() => chat.active?.vehicle)
const vehicleName = computed(() => [vehicle.value?.make, vehicle.value?.model].filter(Boolean).join(' '))

const status = computed(() => {
  if (conn.state === 'offline') return { label: conn.browserOnline ? 'Service offline' : 'No internet', dot: 'bg-danger', ping: false }
  if (conn.state === 'checking') return { label: 'Connecting', dot: 'bg-warn', ping: true }
  if (conn.mode === 'mock') return { label: 'Demo mode', dot: 'bg-info', ping: false }
  if (conn.llmAvailable === false) return { label: 'Live · Offline mode', dot: 'bg-warn', ping: false }
  return { label: 'Live · Bedrock', dot: 'bg-ok', ping: true }
})

const themeIcon = computed(() => ({ system: Monitor, light: Sun, dark: Moon })[theme.pref.value])
</script>

<template>
  <header class="glass relative z-10 flex h-14 shrink-0 items-center gap-2 border-b border-line/70 px-3 sm:px-5">
    <button class="icon-btn lg:hidden" aria-label="Open diagnosis history" @click="ui.sidebarOpen = true">
      <Menu class="size-5" />
    </button>

    <div class="min-w-0 flex-1">
      <h1 class="truncate text-sm font-semibold tracking-tight">
        {{ chat.active?.title ?? 'New diagnosis' }}
      </h1>
      <div v-if="vehicle && (vehicle.vin || vehicleName || vehicle.dtc_codes.length)" class="mt-0.5 hidden items-center gap-1.5 overflow-hidden text-[11px] text-muted sm:flex">
        <span v-if="vehicleName" class="truncate">{{ vehicleName }}</span>
        <span v-if="vehicle.vin" class="font-mono">{{ vehicle.vin }}</span>
        <span v-for="c in vehicle.dtc_codes" :key="c" class="rounded-full bg-brand-soft px-1.5 font-mono text-brand-strong">{{ c }}</span>
      </div>
    </div>

    <div
      class="flex items-center gap-2 rounded-full border border-line bg-surface/70 px-2.5 py-1 text-xs font-medium text-fg-soft shadow-xs"
      role="status"
      :title="conn.mode === 'mock' ? 'Using the built-in mock backend. Set VITE_API_BASE_URL to connect to FastAPI.' : 'Connection to the diagnosis service'"
    >
      <span class="relative flex size-2">
        <span v-if="status.ping" class="absolute inline-flex size-full animate-ping rounded-full opacity-60" :class="status.dot" />
        <span class="relative inline-flex size-2 rounded-full" :class="status.dot" />
      </span>
      <span class="hidden sm:inline">{{ status.label }}</span>
    </div>

    <div class="flex items-center">
      <button class="icon-btn" :aria-label="`Theme: ${theme.pref.value}. Click to change.`" :title="`Theme: ${theme.pref.value}`" @click="theme.cycle">
        <component :is="themeIcon" class="size-[18px]" />
      </button>
      <button class="icon-btn" aria-label="New diagnosis (Ctrl+Shift+O)" title="New diagnosis (Ctrl+Shift+O)" @click="chat.startNew(), ui.focusComposer()">
        <SquarePen class="size-[18px]" />
      </button>
    </div>
  </header>
</template>
