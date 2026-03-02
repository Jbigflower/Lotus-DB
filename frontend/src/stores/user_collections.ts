import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { userCollections } from '@/api'
import { CustomListType } from '@/types/user_collection'
import type {
  CustomListRead,
  CustomListCreateRequestSchema,
  CustomListUpdateRequestSchema,
} from '@/types/user_collection'

import type { MovieRead } from '@/types/movie'

export const useUserCollectionsStore = defineStore('userCollections', () => {
  const entities = ref<Record<string, CustomListRead>>({})
  const list = ref<CustomListRead[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const filterType = ref<CustomListType | undefined>(undefined)

  const currentId = ref<string | null>(null)
  const currentCollection = computed<CustomListRead | null>(() => {
    const id = currentId.value
    return id ? entities.value[id] ?? list.value.find((c) => c.id === id) ?? null : null
  })

  const moviesById = ref<Record<string, MovieRead[]>>({})
  const currentMovies = computed<MovieRead[]>(() => {
    const id = currentId.value
    return id ? moviesById.value[id] ?? [] : []
  })

  const listMeta = ref({ total: 0, page: 1, size: 20, pages: 0 })
  const favorites = computed<CustomListRead[]>(() => list.value.filter((c) => c.type === CustomListType.FAVORITE))
  const watchlist = computed<CustomListRead[]>(() => list.value.filter((c) => c.type === CustomListType.WATCHLIST))
  const customlists = computed<CustomListRead[]>(() => list.value.filter((c) => c.type === CustomListType.CUSTOMLIST))

  async function fetchList(
    token: string,
    type?: CustomListType,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const res = await userCollections.listUserCollections(token, type, options)
      list.value = res.items ?? []
      listMeta.value = {
        total: res.total ?? list.value.length,
        page: res.page ?? 1,
        size: res.size ?? list.value.length,
        pages: res.pages ?? 1,
      }
      const merged: Record<string, CustomListRead> = { ...entities.value }
      for (const item of list.value) merged[item.id] = item
      entities.value = merged
      if (type !== undefined) filterType.value = type
      return res
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchById(
    token: string,
    collectionId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const c = await userCollections.getUserCollection(token, collectionId, options)
      entities.value = { ...entities.value, [c.id]: c }
      currentId.value = c.id
      return c
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchMovies(
    token: string,
    collectionId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const movies = await userCollections.getCollectionMovies(token, collectionId, options)
      moviesById.value = { ...moviesById.value, [collectionId]: movies }
      currentId.value = collectionId
      return movies
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function create(
    token: string,
    payload: CustomListCreateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const c = await userCollections.createUserCollection(token, payload, options)
      entities.value = { ...entities.value, [c.id]: c }
      list.value = [c, ...list.value]
      return c
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function update(
    token: string,
    collectionId: string,
    patch: CustomListUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const c = await userCollections.updateUserCollection(token, collectionId, patch, options)
      entities.value = { ...entities.value, [c.id]: c }
      const idx = list.value.findIndex((i) => i.id === c.id)
      if (idx >= 0) list.value.splice(idx, 1, c)
      return c
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function remove(
    token: string,
    collectionId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const c = await userCollections.deleteUserCollection(token, collectionId, options)
      const idx = list.value.findIndex((i) => i.id === collectionId)
      if (idx >= 0) list.value.splice(idx, 1)
      entities.value = { ...entities.value, [c.id]: c }
      if (currentId.value === collectionId) currentId.value = null
      delete moviesById.value[collectionId]
      return c
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function addMovies(
    token: string,
    collectionId: string,
    movieIds: string[],
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    await userCollections.addMoviesToCollection(token, collectionId, movieIds, options)
    await fetchById(token, collectionId, options)
    return fetchMovies(token, collectionId, options)
  }

  async function removeMovies(
    token: string,
    collectionId: string,
    movieIds: string[],
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    await userCollections.removeMoviesFromCollection(token, collectionId, movieIds, options)
    await fetchById(token, collectionId, options)
    return fetchMovies(token, collectionId, options)
  }

  function setFilterType(type?: CustomListType) {
    filterType.value = type
  }

  function select(collectionId: string | null) {
    currentId.value = collectionId
  }

  function clearList() {
    list.value = []
    entities.value = {}
    listMeta.value = { total: 0, page: 1, size: 20, pages: 0 }
  }

  function clearMovies(collectionId?: string) {
    if (collectionId) delete moviesById.value[collectionId]
    else moviesById.value = {}
  }

  return {
    entities,
    list,
    listMeta,
    loading,
    error,
    filterType,
    currentId,
    currentCollection,
    moviesById,
    currentMovies,
    favorites,
    watchlist,
    customlists,
    fetchList,
    fetchById,
    fetchMovies,
    create,
    update,
    remove,
    addMovies,
    removeMovies,
    setFilterType,
    select,
    clearList,
    clearMovies,
  }
})
