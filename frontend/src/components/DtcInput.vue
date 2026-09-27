<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { ref, useId } from 'vue'
import { config } from '@/config'
import { isValidDtc, splitDtcInput } from '@/lib/validators'

const codes = defineModel<string[]>({ required: true })
const pending = ref('')
const error = ref('')
const id = useId()

/** Commit whatever is typed; returns false if something invalid is left. */
function commit(): boolean {
  const parts = splitDtcInput(pending.value)
  if (!parts.length) return true
  const invalid = parts.filter((p) => !isValidDtc(p))
  const valid = parts.filter((p) => isValidDtc(p) && !codes.value.includes(p))
  const room = config.maxDtcCodes - codes.value.length
  codes.value = [...codes.value, ...valid.slice(0, Math.max(0, room))]
  if (invalid.length) {
    pending.value = invalid.join(' ')
    error.value = `“${invalid[0]}” isn’t a valid OBD-II code (e.g. P0301, C0035, U0100).`
    return false
  }
  if (valid.length > room) error.value = `Up to ${config.maxDtcCodes} codes per diagnosis.`
  else error.value = ''
  pending.value = ''
  return true
}

function onKeydown(e: KeyboardEvent) {
  if (['Enter', ',', ' ', 'Tab'].includes(e.key) && pending.value.trim()) {
    if (e.key !== 'Tab') e.preventDefault()
    commit()
  } else if (e.key === 'Backspace' && !pending.value && codes.value.length) {
    codes.value = codes.value.slice(0, -1)
  }
}

function remove(code: string) {
  codes.value = codes.value.filter((c) => c !== code)
}

defineExpose({ commit })
</script>

<template>
  <div>
    <label :for="id" class="label">Fault codes (DTC)</label>
    <div
      class="flex min-h-[38px] flex-wrap items-center gap-1.5 rounded-lg border bg-surface px-2 py-1.5 transition-colors focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20"
      :class="error ? 'border-danger' : 'border-line'"
      @click="($refs.field as HTMLInputElement)?.focus()"
    >
      <span v-for="c in codes" :key="c" class="inline-flex items-center gap-1 rounded-md bg-brand-soft py-0.5 pr-1 pl-2 font-mono text-xs font-medium text-brand-strong">
        {{ c }}
        <button type="button" class="rounded p-0.5 hover:bg-brand/15" :aria-label="`Remove ${c}`" @click.stop="remove(c)"><X class="size-3" /></button>
      </span>
      <input
        :id="id"
        ref="field"
        v-model="pending"
        class="min-w-24 flex-1 bg-transparent font-mono text-sm uppercase outline-none placeholder:font-sans placeholder:text-muted/70 placeholder:normal-case"
        :placeholder="codes.length ? 'Add another' : 'e.g. P0301 — press Enter'"
        autocomplete="off"
        autocapitalize="characters"
        spellcheck="false"
        :aria-invalid="!!error"
        :aria-describedby="error ? `${id}-err` : undefined"
        @keydown="onKeydown"
        @blur="commit"
        @paste.prevent="(e: ClipboardEvent) => { pending += e.clipboardData?.getData('text') ?? ''; commit() }"
      />
    </div>
    <p v-if="error" :id="`${id}-err`" class="mt-1 text-xs text-danger">{{ error }}</p>
  </div>
</template>
