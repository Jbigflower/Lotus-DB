<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 selectedTags/languages；监听 @update:selectedTags/@update:language。
 *
 * 设计思路：
 * - 将标签选择与语言选择分组；通过最少事件实现外部状态更新。
 * - 标签列表可由容器层替换为后端返回的数据集。
 *
 * 页面表现（PlainText）：
 * - 标签按钮（可切换选中状态）与语言下拉选择。
 */
const props = defineProps<{
  selectedTags?: string[]
  languages?: string[]
}>()

const emit = defineEmits<{
  (e: 'update:selectedTags', v: string[]): void
  (e: 'update:language', v: string): void
}>()

function toggleTag(tag: string) {
  const set = new Set(props.selectedTags ?? [])
  if (set.has(tag)) set.delete(tag)
  else set.add(tag)
  emit('update:selectedTags', Array.from(set))
}
</script>

<template>
  <section class="filter-panel">
    <header>筛选</header>
    <div class="tags">
      <button
        v-for="t in ['动作','科幻','剧情','喜剧']"
        :key="t"
        type="button"
        :class="{ active: props.selectedTags?.includes(t) }"
        @click="toggleTag(t)"
      >
        #{{ t }}
      </button>
    </div>

    <div class="lang">
      <label>语言</label>
      <select
        class="select"
        @change="emit('update:language', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">自动</option>
        <option value="zh">中文</option>
        <option value="en">English</option>
      </select>
    </div>
  </section>
</template>