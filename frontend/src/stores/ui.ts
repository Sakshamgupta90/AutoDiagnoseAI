import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Attachment, VehicleContext } from '@/types/chat'

/** Full-resolution object URLs for photos added this session (not persisted). */
export const fullImageUrls = new Map<string, string>()

export interface ComposerDraft {
  text: string
  vehicle?: Partial<VehicleContext>
}

export const useUiStore = defineStore('ui', () => {
  const sidebarOpen = ref(false)
  const lightbox = ref<Attachment | null>(null)
  /** Set by example prompts / "edit and retry"; the composer consumes it. */
  const draft = ref<ComposerDraft | null>(null)
  const focusComposerTick = ref(0)

  return {
    sidebarOpen,
    lightbox,
    draft,
    focusComposerTick,
    openLightbox: (a: Attachment) => (lightbox.value = a),
    closeLightbox: () => (lightbox.value = null),
    setDraft: (d: ComposerDraft) => (draft.value = d),
    focusComposer: () => focusComposerTick.value++,
  }
})
