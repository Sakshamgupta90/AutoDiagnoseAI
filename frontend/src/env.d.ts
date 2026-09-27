/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_USE_MOCK?: string
  readonly VITE_HEALTH_PATH?: string
  readonly VITE_CURRENCY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
