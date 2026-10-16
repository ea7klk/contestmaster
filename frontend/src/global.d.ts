import 'vue'

declare module 'vue' {
  interface ComponentCustomProperties {
    $tr: (sourceText: string, values?: Record<string, unknown>) => string
  }
}
