<script setup lang="ts">
import { computed } from 'vue'
import { ElTooltip } from 'element-plus'
import Icon from '@/components/icons/Icon.vue'

const props = defineProps<{
  side?: 'left' | 'right'
  visible?: boolean
}>()

const emit = defineEmits<{
  (e: 'screenshot'): void
  (e: 'capture'): void
  (e: 'bookmark'): void
}>()

const posClass = computed(() => (props.side === 'right' ? 'right' : 'left'))
</script>

<template>
  <div v-if="visible !== false" class="overlay-layer">
    <div class="sidebar" :class="posClass">
      <ElTooltip content="截图" placement="right">
        <button class="icon" @click="emit('screenshot')"><Icon name="image-plus" /></button>
      </ElTooltip>
      <ElTooltip content="动图捕获" placement="right">
        <button class="icon" @click="emit('capture')"><Icon name="image-play" /></button>
      </ElTooltip>
      <ElTooltip content="书签截取" placement="right">
        <button class="icon" @click="emit('bookmark')"><Icon name="bookmark-plus" /></button>
      </ElTooltip>
    </div>
  </div>
</template>

<style scoped>
.sidebar { position: absolute; top: 50%; transform: translateY(-50%); display: grid; gap: var(--space-3); }
.sidebar.left { left: var(--space-3); }
.sidebar.right { right: var(--space-3); }
.icon { border: none; background: color-mix(in oklab, #000, white 8%); color: var(--text-on-surface); border-radius: var(--radius-pill); padding: 6px 10px; box-shadow: var(--shadow-1); }
.icon:hover { background: color-mix(in oklab, #000, white 16%); }
</style>