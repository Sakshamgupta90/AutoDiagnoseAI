<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import AppSidebar from '@/components/AppSidebar.vue'
import ChatComposer from '@/components/ChatComposer.vue'
import ChatThread from '@/components/ChatThread.vue'
import EmptyState from '@/components/EmptyState.vue'
import ImageLightbox from '@/components/ImageLightbox.vue'
import StatusBanner from '@/components/StatusBanner.vue'
import ToastHost from '@/components/ToastHost.vue'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'

const chat = useChatStore()
const ui = useUiStore()

function onKeydown(e: KeyboardEvent) {
  const mod = e.metaKey || e.ctrlKey
  if (mod && e.shiftKey && e.key.toLowerCase() === 'o') {
    e.preventDefault()
    chat.startNew()
    ui.focusComposer()
  } else if (e.key === 'Escape' && ui.sidebarOpen) {
    ui.sidebarOpen = false
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="flex h-dvh overflow-hidden bg-bg text-fg">
    <a
      href="#composer"
      class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2"
      >Skip to message box</a
    >
    <AppSidebar />

    <main class="app-glow relative flex min-w-0 flex-1 flex-col">
      <AppHeader />
      <StatusBanner />
      <div class="relative min-h-0 flex-1">
        <ChatThread v-if="chat.active" :key="chat.active.id" :conversation="chat.active" />
        <EmptyState v-else />
      </div>
      <ChatComposer />
    </main>

    <ImageLightbox />
    <ToastHost />
  </div>
</template>
