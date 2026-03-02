<script setup lang="ts">
/**
 * 使用方式：
 * - v-model 风格：监听 @update:query 更新关键字；点击或回车触发 @search。
 *
 * 设计思路：
 * - 轻量输入与动作分离：输入值通过事件回传；触发搜索由容器实现。
 * - 不直接耦合后端字段，提升通用性。
 *
 * 页面表现（PlainText）：
 * - 一个文本输入框与“检索”按钮；回车也会触发检索。
 */
const props = defineProps<{
  query?: string
}>()

const emit = defineEmits<{
  (e: 'update:query', v: string): void
  (e: 'search'): void
}>()

function onSearch() {
  emit('search')
}
</script>

<template>
  <div class="search-bar">
    <input
      class="input"
      :value="props.query ?? ''"
      placeholder="关键词检索"
      @input="emit('update:query', ($event.target as HTMLInputElement).value)"
      @keyup.enter="onSearch"
    />
    <button type="button" class="btn btn-primary" @click="onSearch">检索</button>
  </div>
</template>