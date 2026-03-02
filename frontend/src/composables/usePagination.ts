import { computed } from 'vue'

export function usePagination(listMeta: { page: number; size: number; total: number; pages: number }, setPage: (p: number) => void) {
  const canPrev = computed(() => listMeta.page > 1)
  const canNext = computed(() => listMeta.page < listMeta.pages)
  function prev() { if (canPrev.value) setPage(listMeta.page - 1) }
  function next() { if (canNext.value) setPage(listMeta.page + 1) }
  function toPage(p: number) { if (p >= 1 && p <= listMeta.pages) setPage(p) }
  return { canPrev, canNext, prev, next, toPage }
}