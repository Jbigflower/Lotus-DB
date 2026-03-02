import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { libraries } from '@/api'
import type { ListLibrariesParams } from '@/api/libraries'
import {
  LibraryType,
  type LibraryRead,
  type LibraryCreateRequestSchema,
  type LibraryUpdateRequestSchema,
  type LibraryPageResult,
} from '@/types/library'

export const libraryFieldDefs = [
  { key: 'id', label: 'ID', width: 160 },
  { key: 'user_id', label: '用户ID', width: 160 },
  { key: 'name', label: '名称' },
  { key: 'type', label: '类型', width: 120 },
  { key: 'description', label: '描述' },
  { key: 'root_path', label: '根路径' },
  { key: 'scan_interval', label: '扫描间隔', width: 120 },
  { key: 'auto_import', label: '自动导入', width: 100 },
  { key: 'auto_import_scan_path', label: '自动导入扫描路径' },
  { key: 'auto_import_supported_formats', label: '自动导入支持格式' },
  { key: 'activated_plugins', label: '激活插件' },
  { key: 'is_public', label: '公开', width: 100 },
  { key: 'is_active', label: '已激活', width: 100 },
  { key: 'is_deleted', label: '已删除', width: 100 },
  { key: 'deleted_at', label: '删除时间', width: 180 },
  { key: 'created_at', label: '创建时间', width: 180 },
  { key: 'updated_at', label: '更新时间', width: 180 },
] satisfies Array<{ key: keyof LibraryRead; label: string; width?: number | string }>

export const defaultLibraryActiveKeys = ['id', 'name', 'type', 'created_at'] satisfies Array<keyof LibraryRead>

export const useLibraryStore = defineStore('library', () => {
  // 规范化字典与列表
  const entities = ref<Record<string, LibraryRead>>({})
  const list = ref<LibraryRead[]>([])
  const listMeta = ref({ page: 1, size: 20, total: 0, pages: 0 })

  // 当前选择库
  const currentId = ref<string | null>(null)
  const currentLibrary = computed<LibraryRead | null>(() => {
    const id = currentId.value
    return id ? entities.value[id] ?? list.value.find((l) => l.id === id) ?? null : null
  })

  // 统计缓存（按库）
  const statsById = ref<Record<string, Record<string, unknown>>>({})

  // 列表筛选（与后端参数一致）
  const filters = ref<ListLibrariesParams>({
    library_type: LibraryType.MOVIE,
    page: 1,
    page_size: 20,
    is_active: undefined,
    is_deleted: undefined,
    auto_import: undefined,
    query: undefined,
    only_me: undefined,
  })

  // 通用状态
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 列表查询：获取库列表，支持传入增量筛选参数，结果更新到 list 和 entities。
  async function fetchList(
    token: string,
    partial?: Partial<ListLibrariesParams>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const params: ListLibrariesParams = { ...filters.value, ...(partial ?? {}) }
      const res: LibraryPageResult = await libraries.listLibraries(token, params, options)
      list.value = res.items
      listMeta.value = { page: res.page, size: res.size, total: res.total, pages: res.pages }
      // 写回规范化字典
      const merged: Record<string, LibraryRead> = { ...entities.value }
      for (const item of res.items) merged[item.id] = item
      entities.value = merged
      } catch (e: unknown) {
        if (e instanceof Error) {
          error.value = e.message
        } else {
          error.value = String(e)
        }
      throw e
    } finally {
      loading.value = false
    }
  }

  // 按 ID 查询单个库详情，结果更新到 entities 并设置为当前库（currentId）
  async function fetchById(
    token: string,
    libraryId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const lib = await libraries.getLibrary(token, libraryId, options)
      entities.value = { ...entities.value, [lib.id]: lib }
      currentId.value = lib.id
      return lib
    } catch (e: unknown) {
      if (e instanceof Error) {
          error.value = e.message
        }
      else {
          error.value = String(e)
        }
      throw e
    } finally {
      loading.value = false
    }
  }

  // 创建新库，新库会插入 list 头部和 entities 字典。
  async function create(
    token: string,
    payload: LibraryCreateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const lib = await libraries.createLibrary(token, payload, options)
      entities.value = { ...entities.value, [lib.id]: lib }
      // 新建默认插入到列表头部
      list.value = [lib, ...list.value]
      return lib
    } catch (e: unknown) {
      if (e instanceof Error){
        error.value = e.message
      }
      else{
        error.value = String(e)
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  // 更新指定库，同步更新 list 和 entities 中对应的数据。
  async function update(
    token: string,
    libraryId: string,
    patch: LibraryUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const lib = await libraries.updateLibrary(token, libraryId, patch, options)
      entities.value = { ...entities.value, [lib.id]: lib }
      const idx = list.value.findIndex((i) => i.id === lib.id)
      if (idx >= 0) list.value.splice(idx, 1, lib)
      return lib
    } catch (e: unknown) {
      if (e instanceof Error){
        error.value = e.message
      }
      else{
        error.value = String(e)
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  // 删除库（默认软删），从 list 中移除，同步更新 entities 并清空当前库（若删除的是当前库）。
  async function remove(
    token: string,
    libraryId: string,
    softDelete = true,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const resp = await libraries.deleteLibrary(token, libraryId, softDelete, options)
      const idx = list.value.findIndex((i) => i.id === libraryId)
      if (idx >= 0) list.value.splice(idx, 1)
      const merged = { ...entities.value }
      delete merged[libraryId]
      entities.value = merged
      if (currentId.value === libraryId) currentId.value = null
      return resp
    } catch (e: unknown) {
      if (e instanceof Error){
        error.value = e.message
      }
      else{
        error.value = String(e)
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  // 恢复已删除的库，重新加入 list 和 entities。
  async function restore(
    token: string,
    libraryId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const lib = await libraries.restoreLibrary(token, libraryId, options)
      entities.value = { ...entities.value, [lib.id]: lib }
      // 可选择将其重新插入列表（这里如存在则替换、若不存在则插入头部）
      const idx = list.value.findIndex((i) => i.id === lib.id)
      if (idx >= 0) list.value.splice(idx, 1, lib)
      else list.value = [lib, ...list.value]
      return lib
    } catch (e: unknown) {
      if (e instanceof Error){
        error.value = e.message
      }
      else{
        error.value = String(e)
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  // 启停、公开/私有
  async function setActive(
    token: string,
    libraryId: string,
    isActive: boolean,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const lib = await libraries.setLibraryActive(token, libraryId, isActive, options)
    entities.value = { ...entities.value, [lib.id]: lib }
    const idx = list.value.findIndex((i) => i.id === lib.id)
    if (idx >= 0) list.value.splice(idx, 1, lib)
    return lib
  }

  async function setPublic(
    token: string,
    libraryId: string,
    isPublic: boolean,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const lib = await libraries.setLibraryPublic(token, libraryId, isPublic, options)
    entities.value = { ...entities.value, [lib.id]: lib }
    const idx = list.value.findIndex((i) => i.id === lib.id)
    if (idx >= 0) list.value.splice(idx, 1, lib)
    return lib
  }

  // 扫描与统计
  async function scan(
    token: string,
    libraryId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    return libraries.scanLibrary(token, libraryId, options)
  }

  async function refreshStats(
    token: string,
    libraryId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const data = await libraries.getLibraryStats(token, libraryId, options)
    statsById.value = { ...statsById.value, [libraryId]: data as Record<string, unknown> }
    return data
  }


  // 本地状态设置

  // 更新列表筛选条件（如切换查询 “音乐库”）。
  function setFilters(partial: Partial<ListLibrariesParams>) {
    filters.value = { ...filters.value, ...partial }
  }
  // 设置列表当前页（用于分页切换）。
  function setPage(page: number) {
    filters.value.page = page
  }
  function setPageSize(size: number) {
    filters.value.page_size = size
  }
  function setCurrentLibrary(id: string | null) {
    currentId.value = id
  }

  return {
    // 状态与计算
    entities,
    list,
    listMeta,
    currentId,
    currentLibrary,
    statsById,
    filters,
    loading,
    error,

    // 动作
    fetchList,
    fetchById,
    create,
    update,
    remove,
    restore,
    setActive,
    setPublic,
    scan,
    refreshStats,
    

    // 本地设置
    setFilters,
    setPage,
    setPageSize,
    setCurrentLibrary,
  }
})
