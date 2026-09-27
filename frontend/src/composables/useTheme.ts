import { ref, watchEffect } from 'vue'

export type ThemePref = 'light' | 'dark' | 'system'
const KEY = 'autodiagnose.theme'

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

const pref = ref<ThemePref>(read())
const media = matchMedia('(prefers-color-scheme: dark)')
const systemDark = ref(media.matches)
media.addEventListener('change', (e) => (systemDark.value = e.matches))

watchEffect(() => {
  const dark = pref.value === 'dark' || (pref.value === 'system' && systemDark.value)
  document.documentElement.classList.toggle('dark', dark)
  try {
    localStorage.setItem(KEY, pref.value)
  } catch {
    /* storage unavailable */
  }
})

const order: ThemePref[] = ['system', 'light', 'dark']

export function useTheme() {
  return {
    pref,
    cycle: () => (pref.value = order[(order.indexOf(pref.value) + 1) % order.length]),
  }
}
