<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 title/description/link；监听 @open(link) 进行外部跳转或处理。
 *
 * 设计思路：
 * - 产出结果的统一展示卡片；点击卡片触发打开，链接显示为辅助入口。
 *
 * 页面表现（PlainText）：
 * - 卡片显示标题与描述；可选“跳转”链接；点击卡片触发打开事件。
 */
const props = defineProps<{
  title: string
  description?: string
  link?: string
}>()

const emit = defineEmits<{
  (e: 'open', v?: string): void
}>()
</script>

<template>
  <article class="result-card" @click="emit('open', props.link)">
    <h3 class="title">{{ props.title }}</h3>
    <p v-if="props.description">{{ props.description }}</p>
    <a v-if="props.link" :href="props.link" @click.stop>跳转</a>
  </article>
</template>