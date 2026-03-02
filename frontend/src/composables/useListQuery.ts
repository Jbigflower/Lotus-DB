import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export interface ListQuery {
  query?: string | null
  tags?: string[] | null
  sort_by?: string | null
  sort_dir?: number | null
  page?: number
  size?: number
}

export function useListQuery(initial: ListQuery = { page: 1, size: 20 }) {
  const route = useRoute()
  const router = useRouter()
  const q = ref<ListQuery>({ ...initial })

  function set(partial: Partial<ListQuery>) { q.value = { ...q.value, ...partial } }
  function reset() { q.value = { ...initial } }

  function syncFromRoute() {
    const { query } = route
    set({
      query: (query.q as string) ?? '',
      page: Number(query.page ?? initial.page),
      size: Number(query.size ?? initial.size),
      sort_by: (query.sort_by as string) ?? '',
      sort_dir: query.sort_dir != null ? Number(query.sort_dir) : undefined,
      tags: Array.isArray(query.tags) ? (query.tags as string[]) : (query.tags ? [String(query.tags)] : []),
    })
  }

  async function syncToRoute() {
    await router.replace({
      query: {
        q: q.value.query ?? '',
        page: q.value.page ?? 1,
        size: q.value.size ?? 20,
        sort_by: q.value.sort_by ?? '',
        sort_dir: q.value.sort_dir ?? undefined,
        tags: q.value.tags ?? [],
      },
    })
  }

  watch(() => route.fullPath, syncFromRoute, { immediate: true })
  return { q, set, reset, syncFromRoute, syncToRoute }
}