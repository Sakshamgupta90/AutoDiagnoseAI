<script setup lang="ts">
import { AlertCircle, ArrowUp, Camera, Car, ChevronDown, ImagePlus, Loader2, Square, Upload, X } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, useId, watch } from 'vue'
import DtcInput from '@/components/DtcInput.vue'
import { config } from '@/config'
import { formatBytes, prepareImage, ACCEPT_ATTR } from '@/lib/image'
import { uid } from '@/lib/format'
import { checkVin, normalizeVin } from '@/lib/validators'
import { emptyVehicle, useChatStore } from '@/stores/chat'
import { useToastStore } from '@/stores/toast'
import { fullImageUrls, useUiStore } from '@/stores/ui'
import type { Attachment, VehicleContext } from '@/types/chat'

interface PendingPhoto {
  id: string
  name: string
  size: number
  status: 'processing' | 'ready' | 'error'
  previewUrl?: string
  thumbUrl?: string
  file?: File
  width?: number
  height?: number
  error?: string
}

const chat = useChatStore()
const ui = useUiStore()
const toast = useToastStore()
const fid = useId()

const text = ref('')
const vehicle = reactive<VehicleContext>(emptyVehicle())
const photos = ref<PendingPhoto[]>([])
const showVehicle = ref(false)
const formError = ref('')
const dragging = ref(false)

const textarea = ref<HTMLTextAreaElement>()
const fileInput = ref<HTMLInputElement>()
const cameraInput = ref<HTMLInputElement>()
const dtcInput = ref<InstanceType<typeof DtcInput>>()

const isTouch = matchMedia('(pointer: coarse)').matches
const isNarrow = matchMedia('(max-width: 639px)').matches
const vinCheck = computed(() => checkVin(vehicle.vin))
const processing = computed(() => photos.value.some((p) => p.status === 'processing'))
const readyPhotos = computed(() => photos.value.filter((p) => p.status === 'ready'))
const busy = computed(() => chat.activeBusy)
const charsLeft = computed(() => config.maxSymptomChars - text.value.length)
const canSend = computed(() => !busy.value && !processing.value && text.value.trim().length > 0)
const vehicleSummary = computed(() => {
  const parts = [[vehicle.make, vehicle.model].filter(Boolean).join(' '), vehicle.vin && `VIN …${vehicle.vin.slice(-6)}`, ...vehicle.dtc_codes]
  return parts.filter(Boolean) as string[]
})

/* ---------- per-conversation state ---------- */
const drafts = new Map<string, string>()
watch(
  () => chat.activeId,
  (id, prev) => {
    drafts.set(prev ?? 'new', text.value)
    text.value = drafts.get(id ?? 'new') ?? ''
    Object.assign(vehicle, toRawVehicle(chat.active?.vehicle))
    clearPhotos()
    formError.value = ''
    nextTick(autosize)
  },
)
function toRawVehicle(v?: VehicleContext): VehicleContext {
  return v ? { vin: v.vin, make: v.make, model: v.model, dtc_codes: [...v.dtc_codes] } : emptyVehicle()
}

/* Example prompts and "edit & resend" push a draft into the composer. */
watch(
  () => ui.draft,
  (d) => {
    if (!d) return
    text.value = d.text
    if (d.vehicle) {
      Object.assign(vehicle, emptyVehicle(), { ...d.vehicle, dtc_codes: [...(d.vehicle.dtc_codes ?? [])] })
      showVehicle.value = true
    }
    ui.draft = null
    formError.value = ''
    nextTick(() => {
      autosize()
      textarea.value?.focus()
    })
  },
)
watch(() => ui.focusComposerTick, () => nextTick(() => textarea.value?.focus()))

/* ---------- textarea ---------- */
function autosize() {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  el.style.overflowY = el.scrollHeight > 220 ? 'auto' : 'hidden'
}
watch(text, () => {
  autosize()
  if (formError.value && text.value.trim()) formError.value = ''
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && !isTouch) {
    e.preventDefault()
    submit()
  }
}

/* ---------- photos ---------- */
async function addFiles(list: FileList | File[] | null | undefined) {
  const files = Array.from(list ?? []).filter((f) => f.type.startsWith('image/') || /\.(heic|heif)$/i.test(f.name))
  if (!files.length) return
  const room = config.maxPhotos - photos.value.length
  if (room <= 0) {
    toast.warning(`Up to ${config.maxPhotos} photos per diagnosis`)
    return
  }
  if (files.length > room) toast.warning(`Only the first ${room} photo${room > 1 ? 's were' : ' was'} added`, `Up to ${config.maxPhotos} photos per diagnosis.`)

  for (const file of files.slice(0, room)) {
    const p: PendingPhoto = { id: uid('p'), name: file.name, size: file.size, status: 'processing' }
    photos.value.push(p)
    const item = () => photos.value.find((x) => x.id === p.id)
    try {
      const prepared = await prepareImage(file)
      const target = item()
      if (!target) continue // removed while processing
      Object.assign(target, {
        status: 'ready',
        file: prepared.file,
        thumbUrl: prepared.thumbUrl,
        previewUrl: URL.createObjectURL(prepared.file),
        size: prepared.file.size,
        width: prepared.width,
        height: prepared.height,
      })
    } catch (err) {
      const target = item()
      if (target) Object.assign(target, { status: 'error', error: err instanceof Error ? err.message : 'Couldn’t read this photo.' })
    }
  }
}

function removePhoto(id: string, revoke = true) {
  const p = photos.value.find((x) => x.id === id)
  if (p?.previewUrl && revoke) URL.revokeObjectURL(p.previewUrl)
  photos.value = photos.value.filter((x) => x.id !== id)
}
function clearPhotos(revoke = true) {
  photos.value.forEach((p) => revoke && p.previewUrl && URL.revokeObjectURL(p.previewUrl))
  photos.value = []
}

function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}
function onPaste(e: ClipboardEvent) {
  const files = Array.from(e.clipboardData?.files ?? [])
  if (files.some((f) => f.type.startsWith('image/'))) {
    e.preventDefault()
    addFiles(files)
  }
}

/* Drag and drop anywhere on the page. */
let dragDepth = 0
const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')
function onDragEnter(e: DragEvent) {
  if (!hasFiles(e)) return
  dragDepth++
  dragging.value = true
}
function onDragLeave(e: DragEvent) {
  if (!hasFiles(e)) return
  dragDepth = Math.max(0, dragDepth - 1)
  if (!dragDepth) dragging.value = false
}
function onDragOver(e: DragEvent) {
  if (hasFiles(e)) e.preventDefault()
}
function onDrop(e: DragEvent) {
  if (!hasFiles(e)) return
  e.preventDefault()
  dragDepth = 0
  dragging.value = false
  if (busy.value) return toast.info('Wait for the current diagnosis to finish')
  addFiles(e.dataTransfer?.files)
}
onMounted(() => {
  window.addEventListener('dragenter', onDragEnter)
  window.addEventListener('dragleave', onDragLeave)
  window.addEventListener('dragover', onDragOver)
  window.addEventListener('drop', onDrop)
})
onBeforeUnmount(() => {
  window.removeEventListener('dragenter', onDragEnter)
  window.removeEventListener('dragleave', onDragLeave)
  window.removeEventListener('dragover', onDragOver)
  window.removeEventListener('drop', onDrop)
})

/* ---------- submit ---------- */
function validate(): string {
  if (!text.value.trim()) return 'Describe the symptoms before sending.'
  if (text.value.trim().length < 3) return 'Add a little more detail about the symptoms.'
  if (text.value.length > config.maxSymptomChars) return `Keep the description under ${config.maxSymptomChars} characters.`
  if (processing.value) return 'Photos are still being prepared — one moment.'
  if (vinCheck.value.state === 'invalid') {
    showVehicle.value = true
    return vinCheck.value.message
  }
  if (dtcInput.value && !dtcInput.value.commit()) {
    showVehicle.value = true
    return 'Fix the fault code before sending.'
  }
  return ''
}

async function submit() {
  if (busy.value) return
  formError.value = validate()
  if (formError.value) return

  const ready = readyPhotos.value
  const attachments: Attachment[] = ready.map((p) => ({
    id: p.id,
    name: p.name,
    size: p.size,
    width: p.width ?? 0,
    height: p.height ?? 0,
    thumbUrl: p.thumbUrl ?? '',
  }))
  ready.forEach((p) => p.previewUrl && fullImageUrls.set(p.id, p.previewUrl))
  const files = ready.map((p) => p.file!)
  const failed = photos.value.filter((p) => p.status === 'error').length

  const payload = {
    text: text.value.trim(),
    vehicle: { ...vehicle, vin: normalizeVin(vehicle.vin), make: vehicle.make.trim(), model: vehicle.model.trim(), dtc_codes: [...vehicle.dtc_codes] },
    attachments,
    files,
  }
  text.value = ''
  drafts.delete(chat.activeId ?? 'new')
  clearPhotos(false) // URLs now owned by the lightbox map
  showVehicle.value = false
  if (failed) toast.info(`${failed} photo${failed > 1 ? 's' : ''} skipped`, 'They couldn’t be processed.')
  await chat.send(payload)
}
</script>

<template>
  <div id="composer" class="relative shrink-0 px-3 pt-1 pb-[max(env(safe-area-inset-bottom),0.75rem)] sm:px-6">
    <div class="pointer-events-none absolute inset-x-0 -top-10 h-10 bg-gradient-to-b from-transparent to-bg" aria-hidden="true" />
    <form
      class="relative mx-auto max-w-3xl rounded-[1.4rem] border bg-surface/90 shadow-[0_8px_30px_-12px_rgb(0_0_0/0.18)] backdrop-blur-xl transition focus-within:border-brand/45 focus-within:ring-4 focus-within:ring-brand/10"
      :class="formError ? 'border-danger/60' : 'border-line'"
      novalidate
      @submit.prevent="submit"
    >
      <!-- Vehicle details -->
      <Transition enter-from-class="opacity-0 -translate-y-1" leave-to-class="opacity-0" enter-active-class="transition" leave-active-class="transition duration-100">
        <fieldset v-show="showVehicle" class="grid gap-3 border-b border-line p-3 sm:grid-cols-2">
          <legend class="sr-only">Vehicle details</legend>
          <div class="sm:col-span-2">
            <label :for="`${fid}-vin`" class="label">VIN or chassis number</label>
            <input
              :id="`${fid}-vin`"
              v-model="vehicle.vin"
              class="input font-mono tracking-wide uppercase"
              :class="vinCheck.state === 'invalid' && 'border-danger'"
              maxlength="20"
              placeholder="17-character VIN, e.g. JTDBR32E530012345"
              autocomplete="off"
              autocapitalize="characters"
              spellcheck="false"
              @blur="vehicle.vin = normalizeVin(vehicle.vin)"
            />
            <p v-if="vinCheck.state === 'invalid' || vinCheck.state === 'chassis'" class="mt-1 text-xs" :class="vinCheck.state === 'invalid' ? 'text-danger' : 'text-warn'">
              {{ vinCheck.message }}
            </p>
            <p v-else-if="vinCheck.state === 'valid'" class="mt-1 text-xs text-ok">Valid VIN — the agent will decode make, model and engine.</p>
          </div>
          <div>
            <label :for="`${fid}-make`" class="label">Make</label>
            <input :id="`${fid}-make`" v-model="vehicle.make" class="input" placeholder="e.g. Toyota" maxlength="40" autocomplete="off" />
          </div>
          <div>
            <label :for="`${fid}-model`" class="label">Model</label>
            <input :id="`${fid}-model`" v-model="vehicle.model" class="input" placeholder="e.g. Corolla Altis" maxlength="40" autocomplete="off" />
          </div>
          <div class="sm:col-span-2">
            <DtcInput ref="dtcInput" v-model="vehicle.dtc_codes" />
          </div>
        </fieldset>
      </Transition>

      <!-- Photos -->
      <ul v-if="photos.length" class="flex gap-2 overflow-x-auto px-3 pt-3" aria-label="Attached photos">
        <li v-for="p in photos" :key="p.id" class="group relative shrink-0">
          <div
            class="grid size-16 place-items-center overflow-hidden rounded-xl border bg-surface-2 shadow-xs"
            :class="p.status === 'error' ? 'border-danger/60' : 'border-line'"
            :title="p.error ?? `${p.name} · ${formatBytes(p.size)}`"
          >
            <img v-if="p.thumbUrl" :src="p.thumbUrl" :alt="p.name" class="size-full object-cover" />
            <Loader2 v-else-if="p.status === 'processing'" class="size-4 animate-spin text-muted" />
            <AlertCircle v-else class="size-5 text-danger" />
          </div>
          <button
            type="button"
            class="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full bg-fg text-bg shadow"
            :aria-label="`Remove ${p.name}`"
            @click="removePhoto(p.id)"
          >
            <X class="size-3" />
          </button>
          <span v-if="p.status === 'ready'" class="absolute inset-x-0 bottom-0 rounded-b-lg bg-black/55 px-1 text-center text-[9px] text-white">{{ formatBytes(p.size) }}</span>
        </li>
      </ul>
      <p v-for="p in photos.filter((x) => x.status === 'error')" :key="`err-${p.id}`" class="px-3 pt-1.5 text-xs text-danger">{{ p.error }}</p>

      <label :for="`${fid}-text`" class="sr-only">Describe the symptoms</label>
      <textarea
        :id="`${fid}-text`"
        ref="textarea"
        v-model="text"
        rows="1"
        class="block max-h-[220px] w-full resize-none overflow-hidden bg-transparent px-4 pt-3.5 pb-2 text-[15px] leading-relaxed outline-none placeholder:text-muted/80"
        :placeholder="chat.active ? 'Add findings or ask a follow-up…' : isNarrow ? 'Describe the symptoms…' : 'Describe the symptoms — when it happens, noises, warning lights…'"
        :maxlength="config.maxSymptomChars + 200"
        :aria-invalid="!!formError"
        :aria-describedby="formError ? `${fid}-err` : undefined"
        @keydown="onKeydown"
        @paste="onPaste"
      />

      <p v-if="formError" :id="`${fid}-err`" class="flex items-center gap-1.5 px-4 pb-1 text-xs text-danger" role="alert">
        <AlertCircle class="size-3.5" /> {{ formError }}
      </p>

      <div class="flex items-center gap-1 px-2 pb-2">
        <input ref="fileInput" type="file" :accept="ACCEPT_ATTR" multiple class="hidden" @change="onPick" />
        <input ref="cameraInput" type="file" accept="image/*" capture="environment" class="hidden" @change="onPick" />
        <button type="button" class="icon-btn" :disabled="photos.length >= config.maxPhotos" aria-label="Attach photos" title="Attach photos (or paste / drop)" @click="fileInput?.click()">
          <ImagePlus class="size-[18px]" />
        </button>
        <button v-if="isTouch" type="button" class="icon-btn" :disabled="photos.length >= config.maxPhotos" aria-label="Take a photo" @click="cameraInput?.click()">
          <Camera class="size-[18px]" />
        </button>
        <button
          type="button"
          class="flex h-9 min-w-0 items-center gap-1.5 rounded-full border border-line px-2.5 text-sm transition-colors hover:bg-surface-2"
          :class="showVehicle || vehicleSummary.length ? 'text-fg' : 'text-muted hover:text-fg'"
          :aria-expanded="showVehicle"
          @click="showVehicle = !showVehicle"
        >
          <Car class="size-[18px] shrink-0" />
          <span v-if="!vehicleSummary.length" class="hidden sm:inline">Vehicle & codes</span>
          <span v-else class="flex min-w-0 gap-1 overflow-hidden">
            <span v-for="s in vehicleSummary.slice(0, 3)" :key="s" class="chip shrink-0 font-mono text-[11px]">{{ s }}</span>
            <span v-if="vehicleSummary.length > 3" class="chip shrink-0 text-[11px]">+{{ vehicleSummary.length - 3 }}</span>
          </span>
          <ChevronDown class="size-3.5 shrink-0 text-muted transition-transform" :class="showVehicle && 'rotate-180'" />
        </button>

        <span class="ml-auto" />
        <span v-if="charsLeft < 200" class="px-1 text-xs tabular-nums" :class="charsLeft < 0 ? 'text-danger' : 'text-muted'">{{ charsLeft }}</span>

        <button v-if="busy" type="button" class="grid size-9 place-items-center rounded-full bg-fg text-bg transition hover:opacity-80" aria-label="Stop diagnosis" title="Stop" @click="chat.cancelActive()">
          <Square class="size-3.5 fill-current" />
        </button>
        <button
          v-else
          type="submit"
          class="grid size-9 place-items-center rounded-full bg-brand-gradient text-white shadow-md shadow-indigo-500/30 transition hover:brightness-110 disabled:bg-none disabled:bg-surface-3 disabled:text-muted disabled:shadow-none"
          :disabled="!canSend"
          aria-label="Send for diagnosis"
          title="Send (Enter)"
        >
          <Loader2 v-if="processing" class="size-4 animate-spin" />
          <ArrowUp v-else class="size-[18px]" />
        </button>
      </div>
    </form>
    <p class="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted">
      <span class="hidden sm:inline">Enter to send · Shift+Enter for a new line · Drop or paste photos. </span>AI suggestions must be verified before any repair.
    </p>

    <!-- Drop overlay -->
    <Transition enter-from-class="opacity-0" leave-to-class="opacity-0" enter-active-class="transition" leave-active-class="transition">
      <div v-if="dragging" class="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-bg/80 p-6 backdrop-blur-sm">
        <div class="flex flex-col items-center gap-3 rounded-3xl border-2 border-dashed border-brand px-12 py-10 text-center">
          <Upload class="size-8 text-brand" />
          <p class="text-lg font-semibold">Drop inspection photos</p>
          <p class="text-sm text-muted">JPEG, PNG or WebP · up to {{ config.maxPhotos }} photos · location data is removed</p>
        </div>
      </div>
    </Transition>
  </div>
</template>
