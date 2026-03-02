import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { userAssets } from '@/api'
import type {
  UserAssetRead,
  UserAssetUpdateRequestSchema,
  UserAssetType,
} from '@/types/user_asset'
import type { MovieRead } from '@/types/movie'
import type {
  ListUserAssetsParams,
  UploadUserAssetForm,
} from '@/api/user_assets'

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message
  if (typeof e === 'string') return e
  try { return JSON.stringify(e) } catch { return String(e) }
}

export const useUserAssetsStore = defineStore('userAssets', () => {
  // 规范化字典与列表
  const entities = ref<Record<string, UserAssetRead>>({})
  const list = ref<UserAssetRead[]>([])
  const listMeta = ref({ total: 0, page: 1, size: 20, pages: 0 })

  // 列表筛选（与后端参数一致）
  const filters = ref<ListUserAssetsParams>({
    q: undefined,
    movie_ids: undefined,
    asset_type: undefined,
    tags: undefined,
    is_public: undefined,
    page: 1,
    size: 20,
  })

  // 当前选择资产
  const currentId = ref<string | null>(null)
  const currentAsset = computed<UserAssetRead | null>(() => {
    const id = currentId.value
    return id ? entities.value[id] ?? list.value.find((a) => a.id === id) ?? null : null
  })

  // 多选（批量操作）
  const selectedIds = ref<string[]>([])
  function toggleSelect(id: string) {
    const idx = selectedIds.value.indexOf(id)
    if (idx >= 0) selectedIds.value.splice(idx, 1)
    else selectedIds.value.push(id)
  }
  function selectAllOnPage() {
    const ids = list.value.map((a) => a.id)
    selectedIds.value = Array.from(new Set([...selectedIds.value, ...ids]))
  }
  function clearSelection() {
    selectedIds.value = []
  }

  // 孤立资产（未分配到电影）
  const isolated = ref<UserAssetRead[]>([])

  // 通用状态
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 列表查询
  async function fetchList(
    token: string,
    partial?: Partial<ListUserAssetsParams>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const params: ListUserAssetsParams = { ...filters.value, ...(partial ?? {}) }
      const res = await userAssets.listUserAssets(token, params, options)
      const items = res.items ?? []
      list.value = items
      listMeta.value = {
        total: res.total ?? items.length,
        page: res.page ?? params.page ?? 1,
        size: res.size ?? params.size ?? items.length,
        pages: res.pages ?? 1,
      }
      // 写回规范化字典
      const merged: Record<string, UserAssetRead> = { ...entities.value }
      for (const item of items) merged[item.id] = item
      entities.value = merged
      filters.value = params
      return res
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 详情查询
  async function fetchById(
    token: string,
    assetId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const a = await userAssets.getUserAsset(token, assetId, options)
      entities.value = { ...entities.value, [a.id]: a }
      currentId.value = a.id
      return a
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 上传（文件或本地路径）
  async function upload(
    token: string,
    form: UploadUserAssetForm,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      // 文本资产走专用端点
      if ((form.type === 'note' as unknown as UserAssetType || form.type === 'review' as unknown as UserAssetType) && !form.file && !form.local_path) {
        const created = await userAssets.createTextUserAsset(token, {
          movie_id: form.movie_id,
          type: form.type,
          name: (form.name ?? null) as any,
          is_public: form.is_public,
          tags: (form.tags ?? null) as any,
          related_movie_ids: (form.related_movie_ids ?? null) as any,
          content: String(form.content ?? ''),
        }, options)
        entities.value = { ...entities.value, [created.id]: created }
        if (shouldAddToList(created)) list.value = [created, ...list.value]
        currentId.value = created.id
        return created
      }
      const { asset } = await userAssets.uploadUserAsset(token, form, options)
      entities.value = { ...entities.value, [asset.id]: asset }
      // 若与当前筛选匹配，插入列表头部
      if (shouldAddToList(asset)) list.value = [asset, ...list.value]
      currentId.value = asset.id
      return asset
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 文本创建（显式动作，供页面直接调用）
  async function createText(
    token: string,
    data: {
      movie_id: string;
      type: UserAssetType; // NOTE/REVIEW
      name?: string | null;
      is_public?: boolean;
      tags?: string[] | null;
      related_movie_ids?: string[] | null;
      content: string;
    },
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const created = await userAssets.createTextUserAsset(token, data as any, options)
      entities.value = { ...entities.value, [created.id]: created }
      if (shouldAddToList(created)) list.value = [created, ...list.value]
      currentId.value = created.id
      return created
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 单资产更新
  async function update(
    token: string,
    assetId: string,
    patch: UserAssetUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const updated = await userAssets.updateUserAsset(token, assetId, patch, options)
      entities.value = { ...entities.value, [updated.id]: updated }
      const idx = list.value.findIndex((i) => i.id === updated.id)
      if (idx >= 0) list.value.splice(idx, 1, updated)
      currentId.value = updated.id
      return updated
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 批量更新
  async function updateBatch(
    token: string,
    assetIds: string[],
    patch: UserAssetUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const updatedList = await userAssets.updateUserAssetsBatch(token, assetIds, patch, options)
      for (const a of updatedList) {
        entities.value = { ...entities.value, [a.id]: a }
        const idx = list.value.findIndex((i) => i.id === a.id)
        if (idx >= 0) list.value.splice(idx, 1, a)
      }
      return updatedList
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 单资产删除
  async function remove(
    token: string,
    assetId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const res = await userAssets.deleteUserAsset(token, assetId, options)
      list.value = list.value.filter((a) => a.id !== assetId)
      const merged = { ...entities.value }; delete merged[assetId]
      entities.value = merged
      if (currentId.value === assetId) currentId.value = null
      selectedIds.value = selectedIds.value.filter((id) => id !== assetId)
      return res
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 批量删除
  async function removeBatch(
    token: string,
    assetIds: string[],
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const res = await userAssets.deleteUserAssetsBatch(token, assetIds, options)
      const idSet = new Set(assetIds)
      list.value = list.value.filter((a) => !idSet.has(a.id))
      const merged = { ...entities.value }
      for (const id of assetIds) delete merged[id]
      entities.value = merged
      selectedIds.value = selectedIds.value.filter((id) => !idSet.has(id))
      if (currentId.value && idSet.has(currentId.value)) currentId.value = null
      return res
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 设置公开状态（单个走批量接口）
  async function setPublic(
    token: string,
    assetId: string,
    isPublic: boolean,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const updated = await userAssets.setUserAssetsActiveStatus(token, [assetId], isPublic, options)
    for (const a of updated) {
      entities.value = { ...entities.value, [a.id]: a }
      const idx = list.value.findIndex((i) => i.id === a.id)
      if (idx >= 0) list.value.splice(idx, 1, a)
    }
    return updated[0]
  }

  // 批量设置公开状态
  async function setPublicBatch(
    token: string,
    assetIds: string[],
    isPublic: boolean,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const updated = await userAssets.setUserAssetsActiveStatus(token, assetIds, isPublic, options)
    for (const a of updated) {
      entities.value = { ...entities.value, [a.id]: a }
      const idx = list.value.findIndex((i) => i.id === a.id)
      if (idx >= 0) list.value.splice(idx, 1, a)
    }
    return updated
  }

  // 孤立资产列表
  async function fetchIsolated(
    token: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const res = await userAssets.listIsolatedAssets(token, options)
      isolated.value = res
      // 也写回 entities，便于复用
      const merged: Record<string, UserAssetRead> = { ...entities.value }
      for (const item of res) merged[item.id] = item
      entities.value = merged
      return res
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // 分配资产到电影
  async function allocate(
    token: string,
    allocateMap: Record<string, string[]>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true; error.value = null
    try {
      const res = await userAssets.allocateAssets(token, allocateMap, options)
      for (const a of res) {
        entities.value = { ...entities.value, [a.id]: a }
        const idx = list.value.findIndex((i) => i.id === a.id)
        if (idx >= 0) list.value.splice(idx, 1, a)
      }
      // 可能不再孤立，移除 isolated 中对应项
      const idSet = new Set(Object.keys(allocateMap))
      isolated.value = isolated.value.filter((a) => !idSet.has(a.id))
      return res
    } catch (e: unknown) {
      error.value = toMessage(e); throw e
    } finally {
      loading.value = false
    }
  }

  // Router ping（健康检查）
  async function pingRouter(options?: { baseURL?: string; signal?: AbortSignal }) {
    return userAssets.ping(options)
  }

  // 辅助：筛选、选择、清理
  function setFilters(partial?: Partial<ListUserAssetsParams>) {
    filters.value = { ...filters.value, ...(partial ?? {}) }
  }
  function clearFilters() {
    filters.value = { q: undefined, movie_ids: undefined, asset_type: undefined, tags: undefined, is_public: undefined, page: 1, size: 20 }
  }
  function select(assetId: string | null) {
    currentId.value = assetId
  }
  function clearList() {
    list.value = []
    listMeta.value = { total: 0, page: 1, size: filters.value.size ?? 20, pages: 0 }
  }
  function clearIsolated() {
    isolated.value = []
  }
  function setPage(page: number) {
    filters.value.page = page
  }
  function setPageSize(size: number) {
    filters.value.size = size
  }

  // 判断是否加入当前列表（用于上传后）
  function shouldAddToList(a: UserAssetRead): boolean {
    const f = filters.value
    if (f.movie_ids && f.movie_ids.length > 0 && !f.movie_ids.includes(a.movie_id)) return false
    if (f.is_public !== undefined && a.is_public !== f.is_public) return false
    if (f.asset_type && f.asset_type.length > 0 && !f.asset_type.includes(a.type as UserAssetType)) return false
    if (f.tags && f.tags.length > 0) {
      for (const t of f.tags) if (!a.tags.includes(t)) return false
    }
    return true
  }

  return {
    entities,
    list,
    listMeta,
    filters,
    currentId,
    currentAsset,
    selectedIds,
    isolated,
    loading,
    error,
    // Actions
    fetchList,
    fetchById,
    upload,
    update,
    updateBatch,
    remove,
    removeBatch,
    setPublic,
    setPublicBatch,
    fetchIsolated,
    allocate,
    pingRouter,
    createText,
    // Helpers
    setFilters,
    clearFilters,
    select,
    toggleSelect,
    selectAllOnPage,
    clearSelection,
    clearList,
    clearIsolated,
    setPage,
    setPageSize,
  }
})