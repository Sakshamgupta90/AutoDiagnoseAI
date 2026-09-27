<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { formatBytes } from '@/lib/image'
import { fullImageUrls, useUiStore } from '@/stores/ui'

const ui = useUiStore()
const closeBtn = ref<HTMLButtonElement>()
const src = computed(() => (ui.lightbox ? (fullImageUrls.get(ui.lightbox.id) ?? ui.lightbox.thumbUrl) : ''))

watch(
  () => ui.lightbox,
  (a) => a && nextTick(() => closeBtn.value?.focus()),
)
</script>

<template>
  <Transition enter-from-class="opacity-0" leave-to-class="opacity-0" enter-active-class="transition" leave-active-class="transition">
    <div
      v-if="ui.lightbox"
      class="fixed inset-0 z-50 flex flex-col bg-black/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      :aria-label="ui.lightbox.name"
      @click.self="ui.closeLightbox()"
      @keydown.esc="ui.closeLightbox()"
    >
      <div class="flex items-center gap-3 text-sm text-white/80">
        <span class="min-w-0 flex-1 truncate">{{ ui.lightbox.name }} · {{ ui.lightbox.width }}×{{ ui.lightbox.height }} · {{ formatBytes(ui.lightbox.size) }}</span>
        <button ref="closeBtn" class="grid size-9 place-items-center rounded-lg text-white hover:bg-white/10" aria-label="Close photo" @click="ui.closeLightbox()">
          <X class="size-5" />
        </button>
      </div>
      <div class="grid min-h-0 flex-1 place-items-center" @click.self="ui.closeLightbox()">
        <img :src="src" :alt="ui.lightbox.name" class="max-h-full max-w-full rounded-lg object-contain shadow-2xl" />
      </div>
    </div>
  </Transition>
</template>
