<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 cover/titleOrigin/titleUser/year/genres/tags/language；
 * - 监听 @change-language/@edit。
 *
 * 设计思路：
 * - 详情页头部信息集中展示；右侧提供语言切换与编辑入口。
 * - 与 MovieRead 解耦，可用投影函数从 release_date/metadata 等派生 year/language。
 *
 * 页面表现（PlainText）：
 * - 左侧封面图（无则占位）；右侧标题（含原文）、年份、类型、标签；语言选择与编辑按钮。
 */
const props = defineProps<{
  cover?: string
  titleOrigin: string
  titleUser?: string
  year?: number
  genres?: string[]
  tags?: string[]
  language?: string
}>()

const emit = defineEmits<{
  (e: 'change-language', v: string): void
  (e: 'edit'): void
}>()
</script>

<template>
  <header class="movie-details-header">
    <div class="cover">
      <img v-if="props.cover" :src="props.cover" :alt="props.titleOrigin" />
      <div v-else class="cover--placeholder">No Cover</div>
    </div>
    <div class="info">
      <h2 class="title">
        {{ props.titleUser ?? props.titleOrigin }}
        <small v-if="props.titleUser">（原文：{{ props.titleOrigin }}）</small>
      </h2>
      <p class="meta">
        <span v-if="props.year">{{ props.year }}</span>
        <span v-if="props.genres?.length"> · {{ props.genres.join('/') }}</span>
      </p>
      <ul class="tags" v-if="props.tags?.length">
        <li v-for="t in props.tags" :key="t" class="tag">#{{ t }}</li>
      </ul>

      <div class="actions">
        <label>语言</label>
        <select
          :value="props.language ?? ''"
          @change="emit('change-language', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">自动</option>
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
        <button type="button" @click="emit('edit')">编辑</button>
      </div>
    </div>
  </header>
</template>