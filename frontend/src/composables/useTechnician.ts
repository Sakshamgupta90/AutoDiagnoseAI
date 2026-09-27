import { ref, watch } from 'vue'

const KEY = 'autodiagnose.technician'

function read(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

const technicianId = ref(read())
watch(technicianId, (v) => {
  try {
    localStorage.setItem(KEY, v.trim())
  } catch {
    /* storage unavailable */
  }
})

/** The technician ID remembered on this device, used to pre-fill sign-off forms. */
export function useTechnician() {
  return technicianId
}
