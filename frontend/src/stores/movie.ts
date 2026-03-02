import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { movies } from '@/api'
import type {
  MovieRead,
  MoviePageResult,
  MovieCreateRequestSchema,
  MovieUpdateRequestSchema,
} from '@/types/movie'
import { useUserStore } from './user'
import { useUserCollectionsStore } from './user_collections'
import { CustomListType } from '@/types/user_collection'
import { ElMessage } from 'element-plus'

export interface MovieListParams {
  library_id?: string | null
  query?: string | null
  genres?: string[] | null
  min_rating?: number | null
  max_rating?: number | null
  start_date?: string | null
  end_date?: string | null
  tags?: string[] | null
  page?: number
  size?: number
  sort_by?: string | null
  sort_dir?: number | null
}

export const useMovieStore = defineStore('movie', () => {
  const entities = ref<Record<string, MovieRead>>({})
  const list = ref<MovieRead[]>([])
  const listMeta = ref({ page: 1, size: 20, total: 0, pages: 0 })

  const lastCreateTaskId = ref<string | null>(null)

  const currentId = ref<string | null>(null)
  const currentMovie = computed<MovieRead | null>(() => {
    const id = currentId.value
    return id ? entities.value[id] ?? list.value.find((m) => m.id === id) ?? null : null
  })

  const filters = ref<MovieListParams>({
    library_id: null,
    query: '',
    genres: [],
    min_rating: undefined,
    max_rating: undefined,
    start_date: '',
    end_date: '',
    tags: [],
    page: 1,
    size: 20,
    sort_by: '',
    sort_dir: undefined,
  })

  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchList(
    token: string,
    partial?: Partial<MovieListParams>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const params: MovieListParams = { ...filters.value, ...(partial ?? {}) }
      const res: MoviePageResult = await movies.listMovies(token, params, options)
      list.value = res.items
      listMeta.value = { page: res.page, size: res.size, total: res.total, pages: res.pages }
      const merged = { ...entities.value }
      for (const m of res.items) merged[m.id] = m
      entities.value = merged
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchById(
    token: string,
    movieId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const m = await movies.getMovie(token, movieId, options)
      entities.value = { ...entities.value, [m.id]: m }
      currentId.value = m.id
      return m
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function create(
    token: string,
    payload: MovieCreateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const res = await movies.createMovie(token, payload, options)
      const m = res.movie_info
      lastCreateTaskId.value = res.task_id
      entities.value = { ...entities.value, [m.id]: m }
      list.value = [m, ...list.value]
      return m
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function update(
    token: string,
    movieId: string,
    patch: MovieUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const m = await movies.updateMovie(token, movieId, patch, options)
      entities.value = { ...entities.value, [m.id]: m }
      const idx = list.value.findIndex((i) => i.id === m.id)
      if (idx >= 0) list.value.splice(idx, 1, m)
      return m
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function remove(
    token: string,
    movieId: string,
    softDelete = true,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      await movies.deleteMovies(token, movieId, softDelete, options)
      list.value = list.value.filter((i) => i.id !== movieId)
      const merged = { ...entities.value }
      delete merged[movieId]
      entities.value = merged
      if (currentId.value === movieId) currentId.value = null
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchRecent(
    token: string,
    params?: { library_id?: string | null; size?: number },
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const items = await movies.listRecentMovies(token, params, options)
      // 按当前列表语义，选择直接覆盖（如需独立 recent 状态可另加 state）
      list.value = items
      const merged = { ...entities.value }
      for (const m of items) merged[m.id] = m
      entities.value = merged
      listMeta.value = { page: 1, size: items.length, total: items.length, pages: 1 }
      return items
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function importBatch(
    token: string,
    file: File | Blob,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const task = await movies.importMoviesBatch(token, file, undefined, options)
      return task
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function updateMany(
    token: string,
    movieIds: string | string[],
    patch: MovieUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const updated = await movies.updateMovies(token, movieIds, patch, options)
      const merged = { ...entities.value }
      for (const m of updated) {
        merged[m.id] = m
        const idx = list.value.findIndex((i) => i.id === m.id)
        if (idx >= 0) list.value.splice(idx, 1, m)
      }
      entities.value = merged
      return updated
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function restoreMany(
    token: string,
    movieIds: string | string[],
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const restored = await movies.restoreMovies(token, movieIds, options)
      const merged = { ...entities.value }
      for (const m of restored) {
        merged[m.id] = m
        const idx = list.value.findIndex((i) => i.id === m.id)
        if (idx >= 0) list.value.splice(idx, 1, m)
        else list.value.unshift(m)
      }
      entities.value = merged
      return restored
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function removeMany(
    token: string,
    movieIds: string | string[],
    softDelete = true,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const res = await movies.deleteMovies(token, movieIds, softDelete, options)
      const idsArray = Array.isArray(movieIds)
        ? movieIds
        : movieIds.split(",").map((s) => s.trim()).filter(Boolean)
      list.value = list.value.filter((i) => !idsArray.includes(i.id))
      const merged = { ...entities.value }
      for (const id of idsArray) delete merged[id]
      entities.value = merged
      if (currentId.value && idsArray.includes(currentId.value)) currentId.value = null
      return res
    } catch (e: any) {
      error.value = e?.message ?? String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 收藏/稍后看：跨页面统一交互
  const favCollectionId = ref<string | null>(null)
  const watchCollectionId = ref<string | null>(null)
  const opTimers = new Map<string, number>()

  async function ensureCollections(type: 'favorite' | 'watchlist') {
    const userStore = useUserStore()
    const collStore = useUserCollectionsStore()
    const token = userStore.token ?? ''
    if (!token) { ElMessage.error('未登录'); throw new Error('未登录') }
    const uid = userStore.user?.id ?? null
    if (favCollectionId.value) {
      const c = collStore.entities[favCollectionId.value]
      if (!c || (uid && c.user_id !== uid)) favCollectionId.value = null
    }
    if (watchCollectionId.value) {
      const c = collStore.entities[watchCollectionId.value]
      if (!c || (uid && c.user_id !== uid)) watchCollectionId.value = null
    }
    if (type === 'favorite' && !favCollectionId.value) {
      const res = await collStore.fetchList(token, CustomListType.FAVORITE)
      const target = (res.items ?? []).find((i) => i.type === CustomListType.FAVORITE && (!uid || i.user_id === uid))
      if (target?.id) favCollectionId.value = target.id
      if (!favCollectionId.value) throw new Error('收藏片单不存在或不属于当前用户')
      const c = collStore.entities[favCollectionId.value]
      if (uid && c && c.user_id !== uid) { favCollectionId.value = null; throw new Error('收藏片单不属于当前用户') }
    }
    if (type === 'watchlist' && !watchCollectionId.value) {
      const res = await collStore.fetchList(token, CustomListType.WATCHLIST)
      const target = (res.items ?? []).find((i) => i.type === CustomListType.WATCHLIST && (!uid || i.user_id === uid))
      if (target?.id) watchCollectionId.value = target.id
      if (!watchCollectionId.value) throw new Error('待观看片单不存在或不属于当前用户')
      const c = collStore.entities[watchCollectionId.value]
      if (uid && c && c.user_id !== uid) { watchCollectionId.value = null; throw new Error('待观看片单不属于当前用户') }
    }
  }

  function debounceById(id: string, fn: () => void) {
    const t = opTimers.get(id)
    if (t) window.clearTimeout(t)
    const nt = window.setTimeout(fn, 300)
    opTimers.set(id, nt)
  }

  function clearCollectionIds() {
    favCollectionId.value = null
    watchCollectionId.value = null
  }

  async function toggleFavorite(id: string | number) {
    const movieId = String(id)
    debounceById(movieId + ':fav', async () => {
      const userStore = useUserStore()
      const collStore = useUserCollectionsStore()
      const token = userStore.token ?? ''
      if (!token) { ElMessage.error('未登录', { duration: 300 }); return }
      try {
        await ensureCollections('favorite')
        const current = entities.value[movieId]
        const optimistic = current?.is_favoriter === true
        if (optimistic) {
          await collStore.removeMovies(token, favCollectionId.value!, [movieId])
          if (current) current.is_favoriter = false
          ElMessage.success('已移除收藏', { duration: 300 })
        } else {
          await collStore.addMovies(token, favCollectionId.value!, [movieId])
          if (current) current.is_favoriter = true
          ElMessage.success('已加入收藏', { duration: 300 })
        }
      } catch (e) {
        ElMessage.error('收藏操作失败', { duration: 300 })
      }
    })
  }

  async function toggleWatchLater(id: string | number) {
    const movieId = String(id)
    debounceById(movieId + ':later', async () => {
      const userStore = useUserStore()
      const collStore = useUserCollectionsStore()
      const token = userStore.token ?? ''
      if (!token) { ElMessage.error('未登录', { duration: 300 }); return }
      try {
        await ensureCollections('watchlist')
        const current = entities.value[movieId]
        const optimistic = current?.is_watchLater === true
        if (optimistic) {
          await collStore.removeMovies(token, watchCollectionId.value!, [movieId])
          if (current) current.is_watchLater = false
          ElMessage.success('已移除待观看', { duration: 300 })
        } else {
          await collStore.addMovies(token, watchCollectionId.value!, [movieId])
          if (current) current.is_watchLater = true
          ElMessage.success('已加入待观看', { duration: 300 })
        }
      } catch (e) {
        ElMessage.error('待观看操作失败', { duration: 300 })
      }
    })
  }

  async function getCoversSigned(
    token: string,
    ids: string[],
    image: "poster.jpg" | "thumbnail.jpg" | "backdrop.jpg" | "all" = "poster.jpg",
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    return movies.getMovieCoversSigned(token, ids, image, options)
  }

  function setFilters(partial: Partial<MovieListParams>) {
    filters.value = { ...filters.value, ...partial }
  }
  function setPage(page: number) {
    filters.value.page = page
  }
  function setSize(size: number) {
    filters.value.size = size
  }
  function setCurrentMovie(id: string | null) {
    currentId.value = id
  }

  return {
    entities,
    list,
    listMeta,
    currentId,
    currentMovie,
    lastCreateTaskId,
    filters,
    loading,
    error,

    fetchList,
    fetchById,
    create,
    update,
    remove,

    setFilters,
    setPage,
    setSize,
    setCurrentMovie,
  
    fetchRecent,
    importBatch,
    updateMany,
    restoreMany,
    removeMany,
    getCoversSigned,
    toggleFavorite,
    toggleWatchLater,
    clearCollectionIds,
  }
})
