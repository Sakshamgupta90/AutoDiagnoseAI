<script setup lang="ts">
import { Check, Loader2, ShieldAlert, UserCheck, X } from 'lucide-vue-next'
import { computed, ref, useId } from 'vue'
import { useTechnician } from '@/composables/useTechnician'
import type { Decision } from '@/types/diagnosis'

/**
 * Human-in-the-loop decision (Section 7.1).
 * - `senior`: safety-critical or low-confidence plans stay hidden until a
 *   senior technician approves them.
 * - otherwise: the assigned technician accepts or rejects the diagnosis.
 */
const uid = useId()
const props = defineProps<{
  senior: boolean
  reason?: string
  category?: string
  submit: (decision: Decision, technicianId: string, notes: string) => Promise<boolean>
}>()

const technician = useTechnician()
const id = ref(technician.value)
const notes = ref('')
const busy = ref<Decision | null>(null)
const touched = ref(false)

const idError = computed(() => (touched.value && !id.value.trim() ? 'Enter your technician ID to sign off.' : ''))
const needsNotes = ref(false)

async function act(decision: Decision) {
  touched.value = true
  if (!id.value.trim()) return
  if (decision === 'reject' && !notes.value.trim()) {
    needsNotes.value = true
    return
  }
  busy.value = decision
  technician.value = id.value.trim()
  await props.submit(decision, id.value.trim(), notes.value.trim())
  busy.value = null
}
</script>

<template>
  <section
    class="rounded-xl border p-4"
    :class="senior ? 'border-warn/40 bg-warn/5' : 'border-line bg-surface'"
    :aria-label="senior ? 'Senior technician sign-off' : 'Technician review'"
  >
    <div class="flex items-start gap-3">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg" :class="senior ? 'bg-warn/15 text-warn' : 'bg-brand-soft text-brand'">
        <ShieldAlert v-if="senior" class="size-5" />
        <UserCheck v-else class="size-5" />
      </span>
      <div class="min-w-0">
        <h3 class="text-sm font-semibold">{{ senior ? 'Senior technician sign-off required' : 'Review this diagnosis' }}</h3>
        <p class="mt-0.5 text-sm text-fg-soft">
          <template v-if="senior">
            <span v-if="category" class="mr-1 inline-block rounded bg-warn/15 px-1.5 py-px text-xs font-medium text-warn capitalize">{{ category }}</span>
            {{ reason || 'This plan affects a safety-critical system.' }} The repair plan stays hidden until it’s approved.
          </template>
          <template v-else>Accept it to close the job with the confirmed fix, or reject it with a reason.</template>
        </p>
      </div>
    </div>

    <form class="mt-4 grid gap-3 sm:grid-cols-[minmax(0,11rem)_1fr]" @submit.prevent="act('approve')">
      <div>
        <label :for="`tech-${uid}`" class="label">{{ senior ? 'Senior technician ID' : 'Technician ID' }}</label>
        <input
          :id="`tech-${uid}`"
          v-model="id"
          class="input font-mono uppercase"
          placeholder="e.g. T-014"
          autocomplete="off"
          :aria-invalid="!!idError"
          :aria-describedby="idError ? `tech-err-${uid}` : undefined"
          @blur="touched = true"
        />
        <p v-if="idError" :id="`tech-err-${uid}`" class="mt-1 text-xs text-danger">{{ idError }}</p>
      </div>
      <div>
        <label :for="`notes-${uid}`" class="label">Notes <span class="font-normal text-muted">{{ needsNotes ? '(required to reject)' : '(optional)' }}</span></label>
        <input
          :id="`notes-${uid}`"
          v-model="notes"
          class="input"
          :class="needsNotes && !notes.trim() && 'border-danger'"
          :placeholder="senior ? 'e.g. Verified pad thickness on lift' : 'Anything the next technician should know'"
          maxlength="500"
        />
      </div>
      <div class="flex flex-col-reverse gap-2 sm:col-span-2 sm:flex-row sm:justify-end">
        <button type="button" class="btn-secondary" :disabled="!!busy" @click="act('reject')">
          <Loader2 v-if="busy === 'reject'" class="size-4 animate-spin" /><X v-else class="size-4" /> Reject
        </button>
        <button type="submit" class="btn-primary" :disabled="!!busy">
          <Loader2 v-if="busy === 'approve'" class="size-4 animate-spin" /><Check v-else class="size-4" />
          {{ senior ? 'Approve & release plan' : 'Accept diagnosis' }}
        </button>
      </div>
    </form>
  </section>
</template>
