import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface OpsLogItem {
  time: string
  user?: string | null
  action: string
  target?: string | null
  detail?: Record<string, unknown> | null
  result?: 'success' | 'error' | 'cancel'
  message?: string | null
}

export const useOpsLogStore = defineStore('opsLog', () => {
  const items = ref<OpsLogItem[]>([])

  function add(entry: Omit<OpsLogItem, 'time'> & { time?: string }) {
    const time = entry.time ?? new Date().toISOString()
    items.value.unshift({ ...entry, time })
  }

  function clear() { items.value = [] }

  return { items, add, clear }
})

