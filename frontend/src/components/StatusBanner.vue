<script setup lang="ts">
import { RefreshCw, WifiOff } from 'lucide-vue-next'
import { ref } from 'vue'
import { useConnectionStore } from '@/stores/connection'

const conn = useConnectionStore()
const checking = ref(false)

async function recheck() {
  checking.value = true
  await conn.check()
  checking.value = false
}
</script>

<template>
  <div
    v-if="conn.state === 'offline'"
    class="flex items-center gap-3 border-b border-danger/20 bg-danger/10 px-4 py-2 text-sm text-danger"
    role="alert"
  >
    <WifiOff class="size-4 shrink-0" />
    <p class="min-w-0 flex-1">
      <span class="font-medium">{{ conn.browserOnline ? 'Can’t reach the diagnosis service.' : 'You’re offline.' }}</span>
      <span class="hidden text-danger/80 sm:inline"> Your history stays available; new diagnoses will fail until the connection is back.</span>
    </p>
    <button class="btn-ghost shrink-0 px-2 py-1 text-danger hover:bg-danger/10 hover:text-danger" :disabled="checking" @click="recheck">
      <RefreshCw class="size-3.5" :class="checking && 'animate-spin'" /> Retry
    </button>
  </div>
</template>
