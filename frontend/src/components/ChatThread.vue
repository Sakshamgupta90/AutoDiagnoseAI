<script setup lang="ts">
import { ArrowDown } from 'lucide-vue-next'
import { nextTick, onMounted, ref, watch } from 'vue'
import AssistantMessage from '@/components/AssistantMessage.vue'
import UserMessage from '@/components/UserMessage.vue'
import type { Conversation } from '@/types/chat'

const props = defineProps<{ conversation: Conversation }>()

const scroller = ref<HTMLElement>()
const pinned = ref(true)

function onScroll() {
  const el = scroller.value
  if (!el) return
  pinned.value = el.scrollHeight - el.scrollTop - el.clientHeight < 120
}

function scrollToBottom(smooth = true) {
  const el = scroller.value
  el?.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

onMounted(() => scrollToBottom(false))

// New message: always jump down. Streaming updates: follow only if the user hasn't scrolled up.
watch(
  () => props.conversation.messages.length,
  async () => {
    await nextTick()
    scrollToBottom()
    pinned.value = true
  },
)
watch(
  () => JSON.stringify(props.conversation.messages.at(-1)),
  async () => {
    if (!pinned.value) return
    await nextTick()
    scrollToBottom(false)
  },
)
</script>

<template>
  <div ref="scroller" class="scroll-thin absolute inset-0 overflow-y-auto" @scroll.passive="onScroll">
    <ol class="mx-auto flex max-w-3xl flex-col gap-6 px-3 pt-6 pb-10 sm:px-6" aria-label="Conversation">
      <li v-for="m in conversation.messages" :key="m.id" class="animate-fade-up">
        <UserMessage v-if="m.role === 'user'" :message="m" />
        <AssistantMessage v-else :message="m" :conversation-id="conversation.id" :request="conversation.messages.find((x) => x.id === m.requestId)" />
      </li>
    </ol>

    <Transition enter-from-class="opacity-0 translate-y-2" leave-to-class="opacity-0 translate-y-2" enter-active-class="transition" leave-active-class="transition">
      <button
        v-if="!pinned"
        class="sticky bottom-4 mx-auto flex w-fit items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium shadow-lg hover:bg-surface-2"
        @click="scrollToBottom()"
      >
        <ArrowDown class="size-3.5" /> Jump to latest
      </button>
    </Transition>
  </div>
</template>
