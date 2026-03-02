import { defineStore } from 'pinia'
import { ref } from 'vue'
import { search } from '@/api'
import type { GlobalSearchResult } from '@/types/search'

export const useSearchStore = defineStore('search', () => {
  const query = ref<string>('')
  const page = ref<number>(1)
  const size = ref<number>(20)
  const onlyMe = ref<boolean>(false)
  const activeType = ref<string>('summary')

  const results = ref<GlobalSearchResult | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function searchAction(token: string, q?: string, type?: string) {
    loading.value = true
    error.value = null
    const targetType = type ?? activeType.value
    try {
      const res = await search.globalSearch(token, {
        q: q ?? query.value,
        page: page.value,
        size: size.value,
        only_me: onlyMe.value,
        type: targetType,
      })
      results.value = res
      return res
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  function setQuery(v: string) { query.value = v }
  function setPage(v: number) { page.value = Math.max(1, v) }
  function setSize(v: number) { size.value = Math.max(1, v) }
  function setOnlyMe(v: boolean) { onlyMe.value = v }
  function setActiveType(v: string) { activeType.value = v }
  function reset() {
    query.value = ''
    page.value = 1
    size.value = 20
    onlyMe.value = false
    activeType.value = 'summary'
    results.value = null
    loading.value = false
    error.value = null
  }

  return {
    query,
    page,
    size,
    onlyMe,
    activeType,
    results,
    loading,
    error,
    search: searchAction,
    setQuery,
    setPage,
    setSize,
    setOnlyMe,
    setActiveType,
    reset,
  }
})