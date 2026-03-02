<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElTooltip, ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus'
import Icon from '@/components/icons/Icon.vue'
import PlayerProgressBar from './PlayerProgressBar.vue'
import { formatTime } from '@/utils/formatTime'

const props = defineProps<{
  playing: boolean
  rate: number
  volume: number
  muted: boolean
  bitrates?: number[]
  currentBitrate?: number | null
  current: number
  duration: number
}>()

const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'seek', time: number): void
  (e: 'seekStep', delta: number): void
  (e: 'rate', r: number): void
  (e: 'volume', v: number): void
  (e: 'mute', v: boolean): void
  (e: 'bitrate', br: number | null): void
  (e: 'fullscreen'): void
  (e: 'settings'): void
}>()

const showVol = ref(false)

function onRate(r: number) { emit('rate', r) }
function onBitrate(br: any) { emit('bitrate', br === 'auto' ? null : Number(br)) }
function onVol(e: Event) {
  const v = Number((e.target as HTMLInputElement).value)
  emit('volume', v)
}

function onSeek(t: number) {
  emit('seek', t)
}

const bitrateLabel = computed(() => {
  if (!props.currentBitrate) return '自动'
  const kbps = props.currentBitrate
  if (kbps >= 4000) return '4K' // 假设
  if (kbps >= 2000) return '1080P'
  if (kbps >= 1200) return '720P'
  return `${kbps}P` // 兜底
})
</script>

<template>
  <div class="player-controls-container">
    <!-- 进度条区域 -->
    <div class="progress-section">
      <PlayerProgressBar 
        :current="current" 
        :duration="duration" 
        @seek="onSeek" 
      />
    </div>

    <!-- 按钮行 -->
    <div class="controls-bar">
      <!-- 左侧：播放控制 + 时间 -->
      <div class="group-left">
        <ElTooltip :content="playing ? '暂停' : '播放'" placement="top" :show-after="500">
          <button class="btn-icon" @click="emit('toggle')">
            <Icon :name="playing ? 'pause' : 'play'" />
          </button>
        </ElTooltip>
        
        <div class="time-display">
          <span class="time-current">{{ formatTime(current) }}</span>
          <span class="time-sep">/</span>
          <span class="time-total">{{ formatTime(duration) }}</span>
        </div>
      </div>

      <div class="spacer"></div>

      <!-- 右侧：功能区 -->
      <div class="group-right">
        <!-- 码率 -->
        <ElDropdown @command="onBitrate" placement="top" trigger="click">
          <button class="btn-text" :class="{ 'is-active': currentBitrate }">
            {{ bitrateLabel }}
          </button>
          <template #dropdown>
            <ElDropdownMenu class="player-dropdown">
              <ElDropdownItem :command="'auto'" :class="{ active: !currentBitrate }">自动</ElDropdownItem>
              <ElDropdownItem v-for="b in (bitrates ?? [])" :key="b" :command="b" :class="{ active: currentBitrate === b }">
                {{ b >= 2000 ? (b >= 4000 ? '4K' : '1080P') : (b >= 1200 ? '720P' : `${b} Kbps`) }}
              </ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>

        <!-- 倍速 -->
        <ElDropdown @command="onRate" placement="top" trigger="click">
          <button class="btn-text">
            {{ rate === 1 ? '倍速' : `${rate}x` }}
          </button>
          <template #dropdown>
            <ElDropdownMenu class="player-dropdown">
              <ElDropdownItem v-for="r in [2.0, 1.5, 1.25, 1.0, 0.75, 0.5]" :key="r" :command="r" :class="{ active: rate === r }">
                {{ r.toFixed(1) }}x
              </ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>

        <!-- 音量 -->
        <div class="volume-container" @mouseenter="showVol = true" @mouseleave="showVol = false">
          <button class="btn-icon" @click="emit('mute', !muted)">
            <Icon :name="muted || volume === 0 ? 'volume-x' : (volume < 0.5 ? 'volume-1' : 'volume-2')" />
          </button>
          <div class="volume-slider-wrapper" v-show="showVol">
             <div class="volume-slider-track">
               <input 
                 type="range" 
                 min="0" max="1" step="0.05" 
                 :value="muted ? 0 : volume" 
                 @input="onVol" 
                 class="volume-range"
               />
               <div class="volume-fill" :style="{ height: (muted ? 0 : volume * 100) + '%' }"></div>
             </div>
          </div>
        </div>

        <!-- 设置 -->
        <ElTooltip content="设置" placement="top" :show-after="500">
          <button class="btn-icon" @click="emit('settings')">
            <Icon name="settings" />
          </button>
        </ElTooltip>

        <!-- 全屏 -->
        <ElTooltip content="全屏" placement="top" :show-after="500">
          <button class="btn-icon" @click="emit('fullscreen')">
            <Icon name="fullscreen" />
          </button>
        </ElTooltip>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-controls-container {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding-bottom: 8px;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.75) 0%, rgba(0, 0, 0, 0.3) 60%, transparent 100%);
  display: flex;
  flex-direction: column;
  gap: 4px;
  opacity: 1;
  transition: opacity 0.3s;
}

/* 隐藏状态（可选，如果父组件需要隐藏控制栏） */
/* .player-controls-container.hidden { opacity: 0; pointer-events: none; } */

.progress-section {
  padding-inline: 0; /* PlayerProgressBar 已有 margin */
}

.controls-bar {
  display: flex;
  align-items: center;
  height: 48px;
  padding-inline: 20px;
  gap: 16px;
}

.group-left, .group-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.spacer { flex: 1; }

/* 按钮基础样式 */
button {
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.85);
  transition: color 0.2s, transform 0.1s;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

button:hover {
  color: #fff;
}

button:active {
  transform: scale(0.95);
}

.btn-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
}
.btn-icon:hover {
  background: rgba(255, 255, 255, 0.1);
}

.btn-icon svg {
  width: 24px;
  height: 24px;
  fill: currentColor;
}

.btn-text {
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  min-width: 48px;
}
.btn-text:hover {
  background: rgba(255, 255, 255, 0.1);
}
.btn-text.is-active {
  color: var(--brand, #409eff);
}

/* 时间显示 */
.time-display {
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: rgba(255, 255, 255, 0.9);
  margin-left: 4px;
}
.time-sep { margin: 0 4px; opacity: 0.5; }

/* 音量滑块 */
.volume-container {
  position: relative;
}
.volume-slider-wrapper {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  padding-bottom: 12px;
  /* 增加交互区域 */
}
.volume-slider-track {
  width: 32px;
  height: 100px;
  background: rgba(20, 20, 20, 0.9);
  border-radius: 4px;
  position: relative;
  display: flex;
  justify-content: center;
  padding-block: 10px;
}
.volume-range {
  writing-mode: bt-lr; /* IE/Edge */
  -webkit-appearance: slider-vertical; /* Webkit */
  width: 4px;
  height: 100%;
  cursor: pointer;
  opacity: 0; /* 隐藏原生滑块，使用自定义样式或简单点直接显示原生 */
  position: absolute;
  z-index: 2;
  inset: 0;
  margin: auto;
}

/* 简化版音量条：直接用原生 vertical range，或者自定义样式 */
/* 这里为了美观，我们使用一个简单的背景条 + 填充条 */
.volume-slider-track::before {
  content: '';
  position: absolute;
  bottom: 10px; top: 10px;
  width: 4px;
  background: rgba(255,255,255,0.3);
  border-radius: 2px;
}
.volume-fill {
  position: absolute;
  bottom: 10px;
  width: 4px;
  background: var(--brand, #409eff);
  border-radius: 2px;
  max-height: calc(100% - 20px);
  pointer-events: none;
}
</style>

<style>
/* 全局 Dropdown 样式覆盖 (因为挂载在 body) */
.player-dropdown {
  background: rgba(20, 20, 20, 0.95) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  backdrop-filter: blur(10px);
}
.player-dropdown .el-dropdown-menu__item {
  color: rgba(255, 255, 255, 0.8) !important;
}
.player-dropdown .el-dropdown-menu__item:hover,
.player-dropdown .el-dropdown-menu__item:focus {
  background: rgba(255, 255, 255, 0.1) !important;
  color: #fff !important;
}
.player-dropdown .el-dropdown-menu__item.active {
  color: var(--brand, #409eff) !important;
}
</style>
