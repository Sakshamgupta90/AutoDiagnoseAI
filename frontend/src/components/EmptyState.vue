<script setup lang="ts">
import { ArrowUpRight, BookOpenCheck, Camera, Disc3, Gauge, ShieldCheck, Sparkles, Thermometer, Zap } from 'lucide-vue-next'
import BrandMark from '@/components/BrandMark.vue'
import { useUiStore } from '@/stores/ui'
import type { ComposerDraft } from '@/stores/ui'

const ui = useUiStore()

const examples: Array<{ icon: typeof Gauge; title: string; hint: string; tone: string; draft: ComposerDraft }> = [
  {
    icon: Gauge,
    title: 'Misfire with check-engine light',
    hint: 'P0301 · rough idle when cold',
    tone: 'from-indigo-500/15 to-indigo-500/0 text-indigo-500 dark:text-indigo-300',
    draft: {
      text: 'Rough idle when the engine is cold, check-engine light flashing under acceleration. Customer says it started last week.',
      vehicle: { vin: 'JTDBR32E530012345', make: 'Toyota', model: 'Corolla Altis', dtc_codes: ['P0301'] },
    },
  },
  {
    icon: Disc3,
    title: 'Grinding noise when braking',
    hint: 'Safety-critical · needs sign-off',
    tone: 'from-rose-500/15 to-rose-500/0 text-rose-500 dark:text-rose-300',
    draft: {
      text: 'Loud grinding noise from the front when braking at low speed, steering wheel vibrates slightly when stopping.',
      vehicle: { make: 'Honda', model: 'Civic', dtc_codes: [] },
    },
  },
  {
    icon: Thermometer,
    title: 'Overheating in traffic',
    hint: 'Coolant loss · temp gauge high',
    tone: 'from-amber-500/15 to-amber-500/0 text-amber-500 dark:text-amber-300',
    draft: {
      text: 'Temperature gauge climbs into the red in stop-start traffic. Customer tops up coolant every few weeks, no visible puddle.',
      vehicle: { make: 'Hyundai', model: 'Elantra', dtc_codes: ['P0217'] },
    },
  },
  {
    icon: Zap,
    title: 'Slow crank, no start',
    hint: 'Electrical · dim dashboard',
    tone: 'from-sky-500/15 to-sky-500/0 text-sky-500 dark:text-sky-300',
    draft: {
      text: 'Engine cranks slowly and sometimes won’t start in the morning. Dashboard lights dim while cranking.',
      vehicle: { make: 'Mazda', model: '3', dtc_codes: [] },
    },
  },
]

const features = [
  { icon: BookOpenCheck, text: 'Cited evidence' },
  { icon: Camera, text: 'Photo analysis' },
  { icon: ShieldCheck, text: 'Safety sign-off' },
]
</script>

<template>
  <div class="scroll-thin absolute inset-0 overflow-y-auto">
    <div class="dot-grid pointer-events-none absolute inset-x-0 top-0 h-[480px]" aria-hidden="true" />
    <div class="relative mx-auto flex min-h-full max-w-3xl flex-col justify-center px-4 py-10 sm:px-6">
      <div class="animate-fade-up text-center">
        <div class="relative mx-auto mb-6 w-fit">
          <div class="absolute -inset-6 rounded-full bg-brand-gradient opacity-30 blur-2xl" aria-hidden="true" />
          <div class="relative rounded-2xl shadow-xl shadow-indigo-500/25"><BrandMark :size="56" /></div>
        </div>

        <span class="mb-4 inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/70 px-3 py-1 text-xs font-medium text-fg-soft shadow-xs backdrop-blur">
          <Sparkles class="size-3.5 text-brand" /> Diagnostic copilot for workshop technicians
        </span>

        <h2 class="text-gradient text-[2rem] leading-[1.1] font-semibold tracking-tight text-balance sm:text-5xl">
          What’s wrong with the vehicle?
        </h2>
        <p class="mx-auto mt-4 max-w-lg text-[15px] leading-relaxed text-pretty text-muted">
          Describe the symptoms and add the VIN, fault codes and photos. You’ll get ranked causes with sources, the tests to confirm them, and a parts and labour estimate.
        </p>

        <ul class="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-2 text-xs text-muted">
          <li v-for="f in features" :key="f.text" class="flex items-center gap-1.5">
            <component :is="f.icon" class="size-3.5 text-brand" /> {{ f.text }}
          </li>
        </ul>
      </div>

      <div class="mt-10 grid gap-3 sm:grid-cols-2">
        <button
          v-for="(ex, i) in examples"
          :key="ex.title"
          class="group gradient-border relative flex animate-fade-up items-center gap-3.5 overflow-hidden rounded-2xl p-3.5 text-left shadow-xs transition duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-indigo-500/10"
          :style="{ animationDelay: `${80 + i * 60}ms` }"
          @click="ui.setDraft(ex.draft)"
        >
          <span class="grid size-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br ring-1 ring-line" :class="ex.tone">
            <component :is="ex.icon" class="size-5" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-sm font-medium">{{ ex.title }}</span>
            <span class="mt-0.5 block truncate text-xs text-muted">{{ ex.hint }}</span>
          </span>
          <ArrowUpRight class="size-4 shrink-0 text-muted opacity-0 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100" />
        </button>
      </div>
      <p class="mt-5 text-center text-xs text-muted">Pick an example to prefill the form, or start typing below.</p>
    </div>
  </div>
</template>
