<script setup lang="ts">
/**
 * 使用方式：
 * - 通过 @update:temperature/@update:topP/@update:maxTokens/@update:streaming 进行 v-model 风格双向。
 *
 * 设计思路：
 * - 将常用推理参数集中在一个面板；保持语义清晰与默认值合理。
 *
 * 页面表现（PlainText）：
 * - 数字输入框（Temperature/TopP/MaxTokens）与“流式输出”复选框。
 */
const props = defineProps<{
  temperature?: number
  topP?: number
  maxTokens?: number
  streaming?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:temperature', v: number): void
  (e: 'update:topP', v: number): void
  (e: 'update:maxTokens', v: number): void
  (e: 'update:streaming', v: boolean): void
}>()
</script>

<template>
  <section class="parameter-panel">
    <label>Temperature</label>
    <input
      type="number"
      step="0.1"
      :value="props.temperature ?? 0.7"
      @input="emit('update:temperature', parseFloat(($event.target as HTMLInputElement).value))"
    />
    <label>TopP</label>
    <input
      type="number"
      step="0.1"
      :value="props.topP ?? 0.9"
      @input="emit('update:topP', parseFloat(($event.target as HTMLInputElement).value))"
    />
    <label>Max Tokens</label>
    <input
      type="number"
      :value="props.maxTokens ?? 1024"
      @input="emit('update:maxTokens', parseInt(($event.target as HTMLInputElement).value))"
    />
    <label>
      <input
        type="checkbox"
        :checked="props.streaming ?? true"
        @change="emit('update:streaming', ($event.target as HTMLInputElement).checked)"
      />
      流式输出
    </label>
  </section>
</template>