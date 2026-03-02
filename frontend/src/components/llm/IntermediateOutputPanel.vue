<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 steps（title/content/status）；仅展示中间输出，不持有状态。
 *
 * 设计思路：
 * - 将中间过程透明化；status 控制“进行中/完成”的视觉态。
 *
 * 页面表现（PlainText）：
 * - 列表展示每个步骤：标题（可选）、状态（进行中/完成）、内容（代码块样式）。
 */
export type Step = { title?: string; content: string; status?: 'running' | 'done' }

const props = defineProps<{
  steps: Step[]
}>()
</script>

<template>
  <section class="intermediate-output">
    <header>模型中间过程输出</header>
    <ul>
      <li v-for="(s, i) in props.steps" :key="i">
        <strong v-if="s.title">{{ s.title }}</strong>
        <span v-if="s.status">（{{ s.status === 'running' ? '进行中' : '完成' }}）</span>
        <pre>{{ s.content }}</pre>
      </li>
    </ul>
  </section>
</template>