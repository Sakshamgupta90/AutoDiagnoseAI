<script setup lang="ts">
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, Plus, Search, ShieldAlert, Trash2, X, XCircle } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import BrandMark from '@/components/BrandMark.vue'
import { relativeTime } from '@/lib/format'
import { isInFlight, useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'
import type { AssistantMessage, Conversation } from '@/types/chat'

const chat = useChatStore()
const ui = useUiStore()
const query = ref('')

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return chat.sorted
  return chat.sorted.filter(
    (c) =>
      c.title.toLowerCase().includes(q) ||
      c.vehicle.vin.toLowerCase().includes(q) ||
      `${c.vehicle.make} ${c.vehicle.model}`.toLowerCase().includes(q) ||
      c.vehicle.dtc_codes.some((d) => d.toLowerCase().includes(q)),
  )
})

const groups = computed(() => {
  const startOfToday = new Date().setHours(0, 0, 0, 0)
  const weekAgo = startOfToday - 6 * 86400_000
  const out: Array<{ label: string; items: Conversation[] }> = [
    { label: 'Today', items: [] },
    { label: 'Previous 7 days', items: [] },
    { label: 'Older', items: [] },
  ]
  for (const c of filtered.value) out[c.updatedAt >= startOfToday ? 0 : c.updatedAt >= weekAgo ? 1 : 2].items.push(c)
  return out.filter((g) => g.items.length)
})

type Badge = { icon: typeof Loader2; cls: string; label: string; spin?: boolean }
function statusOf(c: Conversation): Badge {
  const last = [...c.messages].reverse().find((m) => m.role === 'assistant') as AssistantMessage | undefined
  if (!last) return { icon: CircleDashed, cls: 'text-muted', label: 'Draft' }
  if (isInFlight(last.status)) return { icon: Loader2, cls: 'text-brand', label: 'Diagnosing', spin: true }
  if (last.status === 'error' || last.status === 'interrupted') return { icon: AlertTriangle, cls: 'text-danger', label: 'Needs attention' }
  if (last.decision?.decision === 'rejected') return { icon: XCircle, cls: 'text-muted', label: 'Rejected' }
  if (last.feedback) return { icon: CheckCircle2, cls: 'text-ok', label: 'Closed' }
  if (last.diagnosis?.escalation_required && !last.decision) return { icon: ShieldAlert, cls: 'text-warn', label: 'Awaiting sign-off' }
  if (last.decision) return { icon: CheckCircle2, cls: 'text-ok', label: 'Accepted' }
  return { icon: CircleDashed, cls: 'text-info', label: 'Awaiting review' }
}

function open(id: string) {
  chat.select(id)
  ui.sidebarOpen = false
}
function newChat() {
  chat.startNew()
  ui.sidebarOpen = false
  ui.focusComposer()
}
function remove(c: Conversation) {
  if (confirm(`Delete “${c.title}”? This removes it from this browser.`)) chat.remove(c.id)
}
</script>

<template>
  <!-- Mobile backdrop -->
  <Transition enter-from-class="opacity-0" leave-to-class="opacity-0" enter-active-class="transition-opacity" leave-active-class="transition-opacity">
    <div v-if="ui.sidebarOpen" class="fixed inset-0 z-30 bg-black/50 backdrop-blur-[2px] lg:hidden" @click="ui.sidebarOpen = false" />
  </Transition>

  <aside
    class="fixed inset-y-0 left-0 z-40 flex w-[min(20rem,86vw)] flex-col border-r border-line bg-[color-mix(in_oklab,var(--surface-2)_55%,var(--bg))] transition-transform duration-200 lg:static lg:w-72 lg:translate-x-0"
    :class="ui.sidebarOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'"
    aria-label="Diagnosis history"
  >
    <div class="flex items-center gap-2.5 px-4 pt-4 pb-3">
      <BrandMark :size="30" />
      <div class="min-w-0 leading-tight">
        <div class="font-semibold tracking-tight">AutoDiagnose <span class="bg-brand-gradient bg-clip-text text-transparent">AI</span></div>
        <div class="text-[11px] text-muted">Technician diagnostic copilot</div>
      </div>
      <button class="icon-btn ml-auto lg:hidden" aria-label="Close sidebar" @click="ui.sidebarOpen = false">
        <X class="size-4" />
      </button>
    </div>

    <div class="space-y-2 px-3">
      <button class="btn-secondary group w-full justify-start rounded-xl" @click="newChat">
        <span class="grid size-5 place-items-center rounded-md bg-brand-gradient text-white"><Plus class="size-3.5" /></span>
        New diagnosis
        <kbd class="ml-auto hidden rounded-md border border-line bg-surface-2 px-1.5 font-mono text-[10px] text-muted lg:inline">⌘⇧O</kbd>
      </button>
      <label class="relative block">
        <span class="sr-only">Search diagnoses</span>
        <Search class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted" />
        <input v-model="query" type="search" class="input rounded-xl bg-surface/60 py-1.5 pl-8 shadow-none" placeholder="Search VIN, code, symptom…" />
      </label>
    </div>

    <nav class="scroll-thin mt-3 min-h-0 flex-1 overflow-y-auto px-2 pb-3">
      <p v-if="!chat.conversations.length" class="px-3 py-8 text-center text-sm text-muted">
        Your diagnoses will appear here.
      </p>
      <p v-else-if="!groups.length" class="px-3 py-8 text-center text-sm text-muted">No matches for “{{ query }}”.</p>

      <section v-for="g in groups" :key="g.label" class="mb-2">
        <h3 class="px-2.5 pt-3 pb-1.5 text-[11px] font-medium text-muted">{{ g.label }}</h3>
        <ul>
          <li v-for="c in g.items" :key="c.id" class="group relative">
            <button
              class="flex w-full items-start gap-2.5 rounded-xl border px-2.5 py-2 text-left transition-colors"
              :class="c.id === chat.activeId ? 'border-line bg-surface shadow-xs' : 'border-transparent hover:bg-surface/70'"
              :aria-current="c.id === chat.activeId ? 'page' : undefined"
              @click="open(c.id)"
            >
              <component
                :is="statusOf(c).icon"
                class="mt-0.5 size-4 shrink-0"
                :class="[statusOf(c).cls, statusOf(c).spin && 'animate-spin']"
                :aria-label="statusOf(c).label"
              />
              <span class="min-w-0 flex-1 pr-6">
                <span class="block truncate text-sm" :class="c.id === chat.activeId ? 'font-medium text-fg' : 'text-fg-soft'">{{ c.title }}</span>
                <span class="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted">
                  <span class="truncate">{{ statusOf(c).label }}</span>
                  <span aria-hidden="true">·</span>
                  <span class="shrink-0">{{ relativeTime(c.updatedAt) }}</span>
                </span>
              </span>
            </button>
            <button
              class="icon-btn absolute top-1.5 right-1 size-7 opacity-100 focus:opacity-100 lg:opacity-0 lg:group-hover:opacity-100"
              :aria-label="`Delete ${c.title}`"
              @click.stop="remove(c)"
            >
              <Trash2 class="size-3.5" />
            </button>
          </li>
        </ul>
      </section>
    </nav>

    <footer class="border-t border-line px-4 py-3 text-[11px] leading-relaxed text-muted">
      Knowledge base:
      <a class="underline decoration-dotted underline-offset-2 hover:text-fg" href="https://zenodo.org/records/15626055" target="_blank" rel="noopener">Zenodo Automotive Faults Dataset</a>
      (CC BY 4.0). AI suggestions must be verified by a qualified technician.
    </footer>
  </aside>
</template>
