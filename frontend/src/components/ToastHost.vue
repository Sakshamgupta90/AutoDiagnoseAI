<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-vue-next'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const icons = { success: CheckCircle2, error: XCircle, warning: AlertTriangle, info: Info }
const tones = { success: 'text-ok', error: 'text-danger', warning: 'text-warn', info: 'text-info' }
</script>

<template>
  <div class="pointer-events-none fixed inset-x-0 top-3 z-[60] flex flex-col items-center gap-2 px-3 sm:top-auto sm:right-4 sm:bottom-4 sm:left-auto sm:items-end" aria-live="polite">
    <TransitionGroup
      enter-from-class="opacity-0 translate-y-2 sm:translate-y-0 sm:translate-x-4"
      leave-to-class="opacity-0"
      enter-active-class="transition duration-200"
      leave-active-class="transition duration-150"
    >
      <div
        v-for="t in toast.toasts"
        :key="t.id"
        class="pointer-events-auto flex w-full max-w-sm gap-3 rounded-xl border border-line bg-surface p-3 shadow-lg"
        :role="t.kind === 'error' ? 'alert' : 'status'"
      >
        <component :is="icons[t.kind]" class="mt-0.5 size-4 shrink-0" :class="tones[t.kind]" />
        <div class="min-w-0 flex-1 text-sm">
          <p class="font-medium">{{ t.title }}</p>
          <p v-if="t.message" class="mt-0.5 text-fg-soft">{{ t.message }}</p>
        </div>
        <button class="-m-1 grid size-7 shrink-0 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-fg" aria-label="Dismiss" @click="toast.dismiss(t.id)">
          <X class="size-3.5" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
