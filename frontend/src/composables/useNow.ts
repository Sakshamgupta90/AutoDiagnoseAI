import { onScopeDispose, ref, watch, type Ref } from 'vue'

/** A reactive clock that only ticks while `active` is true. */
export function useNow(active: Ref<boolean>, intervalMs = 100) {
  const now = ref(Date.now())
  let timer: ReturnType<typeof setInterval> | undefined

  watch(
    active,
    (on) => {
      clearInterval(timer)
      now.value = Date.now()
      if (on) timer = setInterval(() => (now.value = Date.now()), intervalMs)
    },
    { immediate: true },
  )
  onScopeDispose(() => clearInterval(timer))
  return now
}
