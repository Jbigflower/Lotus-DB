<script setup lang="ts">
import { computed } from 'vue'
import { JsonViewer } from 'vue3-json-viewer'
import 'vue3-json-viewer/dist/index.css'

const props = defineProps<{
  modelValue: boolean
  data: Record<string, unknown>
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// 简单检测暗色模式，实际项目中可以使用 useDark 或 store
const isDark = computed(() => document.documentElement.getAttribute('data-theme') === 'dark')
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="title || '元数据'"
    width="800px"
    class="metadata-viewer-dialog"
    destroy-on-close
  >
    <div class="viewer-container">
      <JsonViewer
        :value="data"
        :expand-depth="5"
        copyable
        boxed
        sort
        :theme="isDark ? 'jv-dark' : 'jv-light'"
      />
    </div>
  </el-dialog>
</template>

<style scoped>
.viewer-container {
  max-height: 70vh;
  overflow-y: auto;
}
</style>
