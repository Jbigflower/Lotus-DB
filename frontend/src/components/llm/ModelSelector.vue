<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 models（label/value）与 selected；监听 @update:selected。
 *
 * 设计思路：
 * - 简化为单一选择控件；容器层维护模型列表与当前选择。
 *
 * 页面表现（PlainText）：
 * - “模型”标签 + 下拉选择，选项显示友好名称。
 */
type ModelItem = { label: string; value: string }
const props = defineProps<{
  models: ModelItem[]
  selected?: string
}>()

const emit = defineEmits<{
  (e: 'update:selected', v: string): void
}>()
</script>

<template>
  <div class="model-selector">
    <label>模型</label>
    <select
      :value="props.selected ?? ''"
      @change="emit('update:selected', ($event.target as HTMLSelectElement).value)"
    >
      <option v-for="m in props.models" :key="m.value" :value="m.value">
        {{ m.label }}
      </option>
    </select>
  </div>
</template>