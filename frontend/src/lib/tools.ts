import { Camera, Car, Database, History, Wrench, type LucideIcon } from 'lucide-vue-next'

interface ToolMeta {
  label: string
  running: string
  icon: LucideIcon
}

const TOOLS: Record<string, ToolMeta> = {
  vin_decode: { label: 'Decoded vehicle', running: 'Decoding VIN / vehicle', icon: Car },
  sqlite_history: { label: 'Checked service history', running: 'Checking service history', icon: History },
  qdrant_search: { label: 'Searched repair knowledge base', running: 'Searching repair knowledge base', icon: Database },
  photo_analysis: { label: 'Analysed inspection photos', running: 'Analysing inspection photos', icon: Camera },
}

export function toolMeta(name: string): ToolMeta {
  return (
    TOOLS[name] ?? {
      label: name.replace(/_/g, ' '),
      running: `Running ${name.replace(/_/g, ' ')}`,
      icon: Wrench,
    }
  )
}
