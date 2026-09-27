import { defineStore } from 'pinia'
import { onScopeDispose, ref } from 'vue'
import { backend } from '@/lib/backend'

export type ConnectionState = 'checking' | 'online' | 'offline'

/** Tracks whether the diagnosis service is reachable, for the header indicator. */
export const useConnectionStore = defineStore('connection', () => {
  const state = ref<ConnectionState>('checking')
  const browserOnline = ref(navigator.onLine)
  const mode = backend.mode

  async function check() {
    if (!navigator.onLine) {
      state.value = 'offline'
      return
    }
    state.value = (await backend.health()) ? 'online' : 'offline'
  }

  const onOnline = () => ((browserOnline.value = true), check())
  const onOffline = () => ((browserOnline.value = false), (state.value = 'offline'))
  window.addEventListener('online', onOnline)
  window.addEventListener('offline', onOffline)
  const timer = setInterval(check, 30_000)
  check()

  onScopeDispose(() => {
    window.removeEventListener('online', onOnline)
    window.removeEventListener('offline', onOffline)
    clearInterval(timer)
  })

  return { state, browserOnline, mode, check }
})
