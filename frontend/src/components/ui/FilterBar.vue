<script setup lang="ts">
type SortOrder = 'asc' | 'desc'
type CardStyle = 'compact' | 'standard' | 'poster'

export interface FilterBarProps {
  query?: string
  language?: string
  selectedTags?: string[]
  sortBy?: string
  sortOrder?: SortOrder
  cardStyle?: CardStyle
}

const props = defineProps<FilterBarProps>()
const emit = defineEmits<{
  (e: 'update:query', v: string): void
  (e: 'update:language', v: string): void
  (e: 'update:selectedTags', v: string[]): void
  (e: 'update:sortBy', v: string): void
  (e: 'update:sortOrder', v: SortOrder): void
  (e: 'update:cardStyle', v: CardStyle): void
  (e: 'random'): void
  (e: 'search'): void
}>()

function onRandom() {
  emit('random')
}
function onSearch() {
  emit('search')
}
</script>

<template>
  <div class="filter-bar">
    <input
      class="input"
      :value="props.query ?? ''"
      placeholder="关键词检索"
      @input="emit('update:query', ($event.target as HTMLInputElement).value)"
      @keyup.enter="onSearch"
    />
    <select
      class="select"
      :value="props.language ?? ''"
      @change="emit('update:language', ($event.target as HTMLSelectElement).value)"
      aria-label="语言"
    >
      <option value="">自动</option>
      <option value="zh">中文</option>
      <option value="en">English</option>
    </select>

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

    <select
      class="select"
      :value="props.cardStyle ?? 'standard'"
      @change="emit('update:cardStyle', ($event.target as HTMLSelectElement).value as CardStyle)"
      aria-label="卡片样式"
    >
      <option value="compact">紧凑</option>
      <option value="standard">标准</option>
      <option value="poster">海报</option>
    </select>

    <button type="button" class="btn" @click="onRandom">随机进入</button>
    <button type="button" class="btn btn-primary" @click="onSearch">检索</button>

    <slot name="extra" />
  </div>
</template>