<script setup lang="ts">
import { ref, computed } from 'vue'
import { formatTime } from '@/utils/formatTime'

const props = defineProps<{
  current: number
  duration: number
}>()

const emit = defineEmits<{
  (e: 'seek', time: number): void
}>()

const container = ref<HTMLElement | null>(null)
const dragging = ref(false)
const dragTime = ref(0)
const hover = ref(false)
const hoverTime = ref(0)
const hoverX = ref(0)

const percent = computed(() => {
  const d = props.duration || 0
  const t = dragging.value ? dragTime.value : (props.current || 0)
  return d > 0 ? Math.min(100, Math.max(0, (t / d) * 100)) : 0
})

function getInfo(e: MouseEvent) {
  if (!container.value) return { time: 0, x: 0 }
  const rect = container.value.getBoundingClientRect()
  const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left))
  const ratio = x / rect.width
  const time = (props.duration || 0) * ratio
  return { time, x }
}

function onMouseMove(e: MouseEvent) {
  const { time, x } = getInfo(e)
  hoverX.value = x
  hoverTime.value = time
  
  if (dragging.value) {
    dragTime.value = time
  }
}

function onMouseDown(e: MouseEvent) {
  dragging.value = true
  const { time, x } = getInfo(e)
  dragTime.value = time
  hoverX.value = x // update hover pos immediately
  
  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
}

function onWindowMouseMove(e: MouseEvent) {
  if (!dragging.value || !container.value) return
  const { time, x } = getInfo(e)
  dragTime.value = time
  hoverX.value = x
  hoverTime.value = time
}

function onWindowMouseUp(e: MouseEvent) {
  if (dragging.value) {
    emit('seek', dragTime.value)
  }
  dragging.value = false
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
}
</script>

<template>
  <div class="progress-container" 
       ref="container"
       @mousedown="onMouseDown"
       @mousemove="onMouseMove"
       @mouseenter="hover = true" 
       @mouseleave="hover = false">
    
    <div class="progress-track">
      <!-- 缓冲条 (预留) -->
      <div class="progress-buffered"></div>
      
      <!-- 播放进度 -->
      <div class="progress-filled" :style="{ width: percent + '%' }">
        <div class="progress-handle" :class="{ 'is-active': hover || dragging }"></div>
      </div>
    </div>

    <!-- 时间提示 -->
    <div v-if="hover || dragging" class="progress-tooltip" :style="{ left: hoverX + 'px' }">
      {{ formatTime(hoverTime) }}
    </div>
  </div>
</template>

<style scoped>
.progress-container {
  position: relative;
  height: 16px;
  display: flex;
  align-items: center;
  cursor: pointer;
  user-select: none;
  touch-action: none;
  margin-inline: 12px; /* 给左右留点空隙，或者由父容器控制 */
}

.progress-track {
  position: relative;
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.25);
  border-radius: 2px;
  transition: height 0.2s, background-color 0.2s;
}

.progress-container:hover .progress-track {
  height: 6px;
  background: rgba(255, 255, 255, 0.35);
}

.progress-filled {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--brand, #409eff);
  border-radius: 2px;
}

.progress-handle {
  position: absolute;
  right: -6px;
  top: 50%;
  transform: translateY(-50%) scale(0);
  width: 14px;
  height: 14px;
  background: #fff;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  transition: transform 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

.progress-handle.is-active {
  transform: translateY(-50%) scale(1);
}

.progress-tooltip {
  position: absolute;
  bottom: 22px;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  z-index: 10;
  backdrop-filter: blur(4px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
</style>
