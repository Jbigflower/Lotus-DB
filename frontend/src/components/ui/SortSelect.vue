<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 sortBy/sortOrder；监听 @update:sortBy/@update:sortOrder。
 * - 可在容器层将 "date/title/rating" 映射到后端实际字段（如 release_date）。
 *
 * 设计思路：
 * - 将排序的 UI 与后端字段解耦；容器处理映射，组件保持中立。
 *
 * 页面表现（PlainText）：
 * - 两个下拉框：排序字段与排序方向（升序/降序）。
 */
type SortOrder = 'asc' | 'desc'
const props = defineProps<{
  sortBy?: string
  sortOrder?: SortOrder
}>()

const emit = defineEmits<{
  (e: 'update:sortBy', v: string): void
  (e: 'update:sortOrder', v: SortOrder): void
}>()
</script>

<template>
  <div class="sort-select">
    <select
      class="select"
      :value="props.sortBy ?? ''"
      @change="emit('update:sortBy', ($event.target as HTMLSelectElement).value)"
      aria-label="排序字段"
    >
      <option value="date">日期</option>
      <option value="title">标题</option>
      <option value="rating">评分</option>
    </select>

    <select
      class="select"
      :value="props.sortOrder ?? 'desc'"
      @change="emit('update:sortOrder', ($event.target as HTMLSelectElement).value as SortOrder)"
      aria-label="排序方向"
    >
      <option value="asc">升序</option>
      <option value="desc">降序</option>
    </select>
  </div>
</template>