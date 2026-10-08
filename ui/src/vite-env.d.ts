/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MONITOR_HOME?: string
  readonly VITE_DEMO_ALERT_EMAIL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
