<script setup lang="ts">
import { computed } from 'vue'

/**
 * PaginationBar：圆润现代风格，SlothUI-like。
 * - 圆形箭头按钮（上一页/下一页）
 * - 中间页码（可省略 ...）
 * - 悬停轻微放大 + 背景色变化
 * - 当前页高亮、禁用态可用性
 * - 响应式居中布局，主题适配
 */
const props = defineProps<{ page: number; pageSize: number; total?: number }>()
const emit = defineEmits<{ (e: 'prev'): void; (e: 'next'): void; (e: 'change', v: number): void }>()

const pageCount = computed(() => (props.total && props.total > 0 ? Math.ceil(props.total / props.pageSize) : 0))
const canPrev = computed(() => props.page > 1)
const canNext = computed(() => pageCount.value > 0 && props.page < pageCount.value)

type PageItem = number | '...'
function makePages(current: number, total: number): PageItem[] {
  if (!total || total <= 0) return []
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  const pages: PageItem[] = []
  const show = (n: number) => pages.push(n)
  const ellipsis = () => pages.push('...')
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  show(1)
  if (start > 2) ellipsis()
  for (let n = start; n <= end; n++) show(n)
  if (end < total - 1) ellipsis()
  show(total)

  // 边界优化：靠近头尾时显示连续段
  if (current <= 3) {
    pages.splice(0, pages.length, 1, 2, 3, 4, '...', total)
  } else if (current >= total - 2) {
    pages.splice(0, pages.length, 1, '...', total - 3, total - 2, total - 1, total)
  }
  // 去重多余省略号
  return pages.filter((v, idx, arr) => (v === '...' ? !(arr[idx - 1] === '...' || arr[idx + 1] === '...') : true))
}

const visiblePages = computed<PageItem[]>(() => makePages(props.page, pageCount.value))

function toPage(v: number) {
  if (v === props.page) return
  emit('change', v)
}
function prev() { if (canPrev.value) emit('prev') }
function next() { if (canNext.value) emit('next') }
</script>

<template>
  <nav class="pagination-bar" aria-label="Pagination">
    <button type="button" class="btn btn-circle" :disabled="!canPrev" @click="prev" aria-label="上一页">
      <span class="arrow">←</span>
    </button>

    <ul class="pages">
      <li v-for="p in visiblePages" :key="p + '-' + pageCount">
        <button
          v-if="p !== '...'"
          type="button"
          class="btn page-btn"
          :class="{ active: p === props.page }"
          @click="toPage(p as number)"
        >{{ p }}</button>
        <span v-else class="ellipsis">…</span>
      </li>
    </ul>

    <button type="button" class="btn btn-circle" :disabled="!canNext" @click="next" aria-label="下一页">
      <span class="arrow">→</span>
    </button>
  </nav>
</template>

<style scoped>
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2);
}

.pages {
  display: flex;
  align-items: center;
  gap: 6px;
  list-style: none;
  margin: 0;
  padding: 0 4px;
}

.btn {
  appearance: none;
  border: none;
  cursor: pointer;
  font: inherit;
  color: var(--text);
  background: var(--surface);
  border-radius: var(--radius-full);
  padding: 8px 12px;
  box-shadow: var(--shadow-sm);
  transition: transform 120ms ease, background-color 120ms ease, opacity 120ms ease;
}

.btn-circle {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.page-btn {
  min-width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
}

.btn:hover:not(:disabled) {
  transform: scale(1.05);
  background: color-mix(in oklab, var(--surface), var(--brand-weak) 12%);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.page-btn.active {
  background: var(--brand);
  color: var(--on-brand, #fff);
}

.ellipsis {
  color: var(--text-muted);
  padding: 0 6px;
}

.arrow {
  display: inline-block;
  font-size: 16px;
  line-height: 1;
}

:global(html[data-theme="light"]) .btn {
  background: color-mix(in oklab, var(--surface), white 8%);
}
:global(html[data-theme="dark"]) .btn {
  background: color-mix(in oklab, var(--surface), black 6%);
}
</style>