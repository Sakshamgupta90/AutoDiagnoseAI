import { config } from '@/config'

export function uid(prefix: string): string {
  const rand = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID().slice(0, 8) : Math.random().toString(36).slice(2, 10)
  return `${prefix}_${Date.now().toString(36)}${rand}`
}

const currencyFmt = new Intl.NumberFormat('en-SG', { style: 'currency', currency: config.currency, maximumFractionDigits: 0 })
export const formatCurrency = (n: number) => currencyFmt.format(n)

export const formatPercent = (v: number) => `${Math.round(v * 100)}%`

export function formatDuration(ms: number): string {
  const s = Math.max(0, ms) / 1000
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
export function relativeTime(ts: number): string {
  const diff = (ts - Date.now()) / 1000
  const abs = Math.abs(diff)
  if (abs < 45) return 'just now'
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  if (abs < 86400 * 7) return rtf.format(Math.round(diff / 86400), 'day')
  return new Date(ts).toLocaleDateString('en-SG', { day: 'numeric', month: 'short' })
}

export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-SG', { hour: 'numeric', minute: '2-digit' })
}

export type ConfidenceBand = 'low' | 'medium' | 'high'
export function confidenceBand(v: number): ConfidenceBand {
  if (v < config.confidenceThreshold) return 'low'
  if (v < 0.75) return 'medium'
  return 'high'
}

/** Render tool key_inputs as short "key: value" pairs. */
export function formatInputs(inputs: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(inputs)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => [k.replace(/_/g, ' '), Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : String(v)])
}
