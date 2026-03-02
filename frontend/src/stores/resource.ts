import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { system } from '@/api'
import type { ResourceUsage } from '@/types/system'

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message
  if (typeof e === 'string') return e
  try { return JSON.stringify(e) } catch { return String(e) }
}

export const useResourceStore = defineStore('resource', () => {
  const usage = ref<ResourceUsage | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const timer = ref<number | null>(null)

  const cpuPercent = computed(() => usage.value?.system.cpu_percent ?? 0)
  const memPercent = computed(() => usage.value?.system.memory_percent ?? 0)
  const memUsedBytes = computed(() => usage.value?.system.memory_used ?? 0)
  const memTotalBytes = computed(() => usage.value?.system.memory_total ?? 0)

  function danger(p: number, threshold = 0.85) { return p >= threshold }
  const cpuDanger = computed(() => danger((cpuPercent.value ?? 0) / 100))
  const memDanger = computed(() => danger((memPercent.value ?? 0) / 100))

  async function fetch(token?: string, options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true; error.value = null
    try {
      usage.value = await system.getResourceUsage(token, options)
      return usage.value
    } catch (e) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  async function startPolling(token?: string, intervalMs = 10000, options?: { baseURL?: string; signal?: AbortSignal }) {
    stopPolling()
    await fetch(token, options)
    timer.value = window.setInterval(() => { fetch(token, options).catch(() => {}) }, Math.max(3000, intervalMs))
  }
  function stopPolling() {
    if (timer.value !== null) { clearInterval(timer.value); timer.value = null }
  }

  function reset() { usage.value = null; loading.value = false; error.value = null; stopPolling() }

  return { usage, loading, error, cpuPercent, memPercent, memUsedBytes, memTotalBytes, cpuDanger, memDanger, fetch, startPolling, stopPolling, reset }
})

