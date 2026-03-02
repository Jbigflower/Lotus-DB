import { watchEffect } from 'vue'

type Message = string | false | null | undefined

export function useUsageCheck(componentName: string, validate: () => Message[]) {
  if (!import.meta?.env?.DEV) return
  watchEffect(() => {
    const msgs = validate().filter(Boolean) as string[]
    for (const msg of msgs) {
      console.warn(`[${componentName}] ${msg}`)
    }
  })
}