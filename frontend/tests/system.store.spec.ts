import { describe, it, expect, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSystemStore } from '@/stores/system'

describe('useSystemStore refresh', () => {
  it('updates health/status/version and timestamps', async () => {
    setActivePinia(createPinia())
    const store = useSystemStore()
    const mockHealth = vi.spyOn(require('@/api').system, 'health').mockResolvedValue({ overall: 'ok', items: [] })
    const mockStatus = vi.spyOn(require('@/api').system, 'status').mockResolvedValue({ timestamp: new Date().toISOString(), app: { svc: 'running' }, db: {} })
    const mockVersion = vi.spyOn(require('@/api').system, 'version').mockResolvedValue({ app_name: 'LotusDB', app_version: '1.0.0', environment: 'prod' })

    const { health, status, version } = await store.refresh()
    expect(health.overall).toBe('ok')
    expect(status.app.svc).toBe('running')
    expect(version.app_name).toBe('LotusDB')
    expect(store.lastUpdated.health).toBeTypeOf('string')
    expect(store.lastUpdated.status).toBeTypeOf('string')
    expect(store.lastUpdated.version).toBeTypeOf('string')

    mockHealth.mockRestore(); mockStatus.mockRestore(); mockVersion.mockRestore()
  })
})

