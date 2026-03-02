<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 items 列表；可选传入 projector(raw) 将任意结构映射为子项组件所需 props。
 * - 透传子项事件：@open/@play/@preview/@toggle-favorite/@toggle-watch-later。
 *
 * 设计思路：
 * - 组合模式：仅负责遍历与事件透传；数据结构转换交由 projector，避免强耦合。
 * - 可扩展：支持 dense 紧凑模式；默认投影兼容 MovieRead 的常见字段。
 * - 新增：支持通过 itemComponent 自定义子项组件，默认使用 MediaCard。
 *
 * 页面表现（PlainText）：
 * - 多张媒体卡片以栅格布局展示；卡片之间留有间距，支持紧凑模式。
 */
import { computed } from 'vue'
import type { Component } from 'vue'
import MediaCard, { type MediaCardProps } from './MediaCard.vue'
import type { MovieRead } from '@/types/movie'

type GridItem = MediaCardProps | MovieRead | Record<string, unknown>

const props = defineProps<{
  items: GridItem[]
  dense?: boolean
  projector?: (raw: GridItem) => Record<string, unknown>
  itemComponent?: Component
}>()

const emit = defineEmits<{
  (e: 'open', id: string | number): void
  (e: 'play', id: string | number): void
  (e: 'preview', id: string | number): void
  (e: 'toggle-favorite', id: string | number): void
  (e: 'toggle-watch-later', id: string | number): void
  (e: 'click-movie', movieId: string | number): void
  (e: 'contextmenu', payload: { id: string; x: number; y: number }): void
}>()

function defaultProject(raw: GridItem): Record<string, unknown> {
  const has = (key: string): boolean => typeof raw === 'object' && raw !== null && key in raw

  const idUnknown = has('id') ? (raw as { id: unknown }).id : undefined
  const id = typeof idUnknown === 'string' || typeof idUnknown === 'number'
    ? idUnknown
    : String(idUnknown ?? Math.random())

  const titleUnknown = has('title') ? (raw as { title: unknown }).title : undefined
  const titleCnUnknown = has('title_cn') ? (raw as { title_cn: unknown }).title_cn : undefined
  const title = typeof titleUnknown === 'string'
    ? titleUnknown
    : (typeof titleCnUnknown === 'string' ? titleCnUnknown : String(titleUnknown ?? id))

  const posterUnknown = has('poster') ? (raw as { poster: unknown }).poster : undefined
  const poster = typeof posterUnknown === 'string' ? posterUnknown : undefined

  const ratingUnknown = has('rating') ? (raw as { rating: unknown }).rating : undefined
  const rating = typeof ratingUnknown === 'number' ? ratingUnknown : undefined

  const tagsUnknown = has('tags') ? (raw as { tags: unknown }).tags : undefined
  const tags = Array.isArray(tagsUnknown) ? (tagsUnknown as string[]) : undefined

  const progressUnknown = has('progressPercent') ? (raw as { progressPercent: unknown }).progressPercent : undefined
  const progressPercent = typeof progressUnknown === 'number' ? progressUnknown : undefined

  const favUnknownA = has('isFavorite') ? (raw as { isFavorite: unknown }).isFavorite : undefined
  const favUnknownB = has('is_favoriter') ? (raw as { is_favoriter: unknown }).is_favoriter : undefined
  const isFavorite = typeof favUnknownA === 'boolean' ? favUnknownA : (typeof favUnknownB === 'boolean' ? favUnknownB : undefined)

  const laterUnknownA = has('inWatchLater') ? (raw as { inWatchLater: unknown }).inWatchLater : undefined
  const laterUnknownB = has('is_watchLater') ? (raw as { is_watchLater: unknown }).is_watchLater : undefined
  const inWatchLater = typeof laterUnknownA === 'boolean' ? laterUnknownA : (typeof laterUnknownB === 'boolean' ? laterUnknownB : undefined)

  return { id, title, poster, rating, tags, progressPercent, isFavorite, inWatchLater }
}

function toProps(raw: GridItem): Record<string, unknown> {
  const projected = (props.projector ?? defaultProject)(raw)
  return projected as Record<string, unknown>
}

function getKey(raw: GridItem, idx: number): string | number {
  if (typeof raw === 'object' && raw !== null && 'id' in raw) {
    const id = (raw as { id: unknown }).id
    if (typeof id === 'string' || typeof id === 'number') return id
  }
  return idx
}

const itemComp = computed(() => props.itemComponent ?? MediaCard)
</script>

<template>
  <section class="media-grid" :class="{ dense: props.dense }">
    <component
      :is="itemComp"
      v-for="(m, i) in props.items"
      :key="getKey(m, i)"
      v-bind="toProps(m)"
      :dense="props.dense"
      @open="emit('open', $event)"
      @play="emit('play', $event)"
      @preview="emit('preview', $event)"
      @toggle-favorite="emit('toggle-favorite', $event)"
      @toggle-watch-later="emit('toggle-watch-later', $event)"
      @click-movie="emit('click-movie', $event)"
      @contextmenu="emit('contextmenu', $event)"
    />
  </section>
</template>

<style scoped>
.media-grid {
  display: grid;
  /* 自适应：通过变量控制卡片最小宽度，随分辨率变化 */
  /* 默认连续缩放：在不同屏宽下平滑调整卡片宽度上限与下限 */
  --card-min-width: clamp(200px, 16vw, 280px);
  grid-template-columns: repeat(auto-fill, minmax(var(--card-min-width), 1fr));
  gap: 1rem; /* 卡片间固定间距 */
  align-items: start;
}

.media-grid.dense {
  /* 紧凑模式：卡片最小宽度更小，间距更小 */
  --card-min-width-dense: clamp(160px, 14vw, 240px);
  grid-template-columns: repeat(auto-fill, minmax(var(--card-min-width-dense), 1fr));
  gap: 0.5rem;
}

/* 分辨率断点微调：兼顾笔记本/中等显示器/超大屏的密度与比例 */
@media (max-width: 1366px) {
  .media-grid { --card-min-width: 200px; }
  .media-grid.dense { --card-min-width-dense: 160px; }
}
@media (min-width: 1367px) and (max-width: 1919px) {
  .media-grid { --card-min-width: 220px; }
  .media-grid.dense { --card-min-width-dense: 180px; }
}
@media (min-width: 1920px) and (max-width: 2560px) {
  .media-grid { --card-min-width: 240px; }
  .media-grid.dense { --card-min-width-dense: 200px; }
}
@media (min-width: 2561px) {
  .media-grid { --card-min-width: 260px; }
  .media-grid.dense { --card-min-width-dense: 220px; }
}
</style>
