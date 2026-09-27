<script setup lang="ts">
import { BookPlus, Loader2 } from 'lucide-vue-next'
import { computed, ref, useId } from 'vue'
import type { FeedbackPayload, RankedCause } from '@/types/diagnosis'

const uid = useId()
const props = defineProps<{
  causes: RankedCause[]
  submit: (payload: FeedbackPayload) => Promise<boolean>
}>()

const OTHER = '__other__'
const choice = ref(props.causes[0]?.cause ?? OTHER)
const otherCause = ref('')
const fix = ref('')
const partCost = ref<number | ''>('')
const labour = ref<number | ''>('')
const busy = ref(false)
const tried = ref(false)

const cause = computed(() => (choice.value === OTHER ? otherCause.value.trim() : choice.value))
const errors = computed(() => ({
  cause: !cause.value ? 'Select or describe the confirmed cause.' : '',
  fix: !fix.value.trim() ? 'Describe the repair that fixed it.' : '',
  partCost: partCost.value !== '' && partCost.value < 0 ? 'Cost can’t be negative.' : '',
  labour: labour.value !== '' && (labour.value < 0 || labour.value > 100) ? 'Enter hours between 0 and 100.' : '',
}))
const valid = computed(() => Object.values(errors.value).every((e) => !e))

async function onSubmit() {
  tried.value = true
  if (!valid.value) return
  busy.value = true
  await props.submit({
    confirmed_cause: cause.value,
    confirmed_fix: fix.value.trim(),
    part_cost: partCost.value === '' ? undefined : Number(partCost.value),
    labour_hours: labour.value === '' ? undefined : Number(labour.value),
  })
  busy.value = false
}
</script>

<template>
  <form class="rounded-xl border border-line bg-surface p-4" novalidate @submit.prevent="onSubmit">
    <div class="flex items-start gap-3">
      <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-ok/10 text-ok"><BookPlus class="size-5" /></span>
      <div>
        <h3 class="text-sm font-semibold">Close the job with the confirmed fix</h3>
        <p class="mt-0.5 text-sm text-fg-soft">The confirmed fix is added to the workshop’s knowledge base, so the next diagnosis like this is faster.</p>
      </div>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2">
      <div class="sm:col-span-2">
        <label :for="`cause-${uid}`" class="label">Confirmed cause</label>
        <select :id="`cause-${uid}`" v-model="choice" class="input">
          <option v-for="c in causes" :key="c.cause" :value="c.cause">{{ c.cause }}</option>
          <option :value="OTHER">Something else…</option>
        </select>
        <input v-if="choice === OTHER" v-model="otherCause" class="input mt-2" placeholder="Describe the actual cause" maxlength="200" />
        <p v-if="tried && errors.cause" class="mt-1 text-xs text-danger">{{ errors.cause }}</p>
      </div>
      <div class="sm:col-span-2">
        <label :for="`fix-${uid}`" class="label">Repair performed</label>
        <textarea :id="`fix-${uid}`" v-model="fix" rows="2" class="input resize-y" placeholder="e.g. Replaced cylinder 1 ignition coil, cleared codes, road-tested 10 km" maxlength="1000" />
        <p v-if="tried && errors.fix" class="mt-1 text-xs text-danger">{{ errors.fix }}</p>
      </div>
      <div>
        <label :for="`cost-${uid}`" class="label">Parts cost <span class="font-normal text-muted">(optional)</span></label>
        <input :id="`cost-${uid}`" v-model.number="partCost" type="number" min="0" step="1" inputmode="decimal" class="input" placeholder="0" />
        <p v-if="tried && errors.partCost" class="mt-1 text-xs text-danger">{{ errors.partCost }}</p>
      </div>
      <div>
        <label :for="`hours-${uid}`" class="label">Labour hours <span class="font-normal text-muted">(optional)</span></label>
        <input :id="`hours-${uid}`" v-model.number="labour" type="number" min="0" max="100" step="0.1" inputmode="decimal" class="input" placeholder="0.0" />
        <p v-if="tried && errors.labour" class="mt-1 text-xs text-danger">{{ errors.labour }}</p>
      </div>
    </div>
    <div class="mt-4 flex justify-end">
      <button type="submit" class="btn-primary w-full sm:w-auto" :disabled="busy">
        <Loader2 v-if="busy" class="size-4 animate-spin" /> Close job
      </button>
    </div>
  </form>
</template>
