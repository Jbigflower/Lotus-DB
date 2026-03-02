<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'

/**
 * 列表页工具栏（单行、图标化）：
 * 左到右：搜索框 | 随机进入 | 视图切换（卡片/列表/大图） | 筛选 | 排序
 * - 搜索：输入即时触发过滤；按 Enter 触发搜索事件
 * - 随机进入：点击触发“掷骰子”旋转/抖动动画，并向上抛出事件
 * - 视图切换：保留三态；当前仅卡片/列表有效，gallery 预留
 */
const props = defineProps<{
  total?: number
  rangeStart?: number
  rangeEnd?: number
  viewMode?: 'card' | 'list' | 'gallery'
  disableViewToggle?: boolean
  disableAdd?: boolean
  hideSearch?: boolean
  addTo?: RouteLocationRaw
  addHandler?: () => void
  showFieldManager?: boolean
  disableRandom?: boolean
}>()

const emit = defineEmits<{
  (e: 'random'): void
  (e: 'toggle-view', mode: 'card' | 'list' | 'gallery'): void
  (e: 'open-sort'): void
  (e: 'open-filter'): void
  (e: 'search', q: string): void
  (e: 'add'): void
}>()

const localView = ref<'card' | 'list' | 'gallery'>(props.viewMode ?? 'card')
function setView(mode: 'card' | 'list' | 'gallery') {
  localView.value = mode
  emit('toggle-view', mode)
}

const quick = ref('')
function triggerSearch() { emit('search', quick.value.trim()) }
function onQuickInput() { emit('search', quick.value) }

// Shuffle 轻微抖动动画
const rolling = ref(false)
function onRandomClick() {
  rolling.value = true
  setTimeout(() => { rolling.value = false }, 420)
  emit('random')
}

// 单图标视图切换：卡片 → 列表 → 大图 → 回到卡片（类型安全映射）
type ViewMode = 'card' | 'list' | 'gallery'
const order = ['card', 'list', 'gallery'] as const
const nextMap: Record<ViewMode, ViewMode> = { card: 'list', list: 'gallery', gallery: 'card' }
function cycleView() { setView(nextMap[localView.value]) }

const router = useRouter()
function onAddClick() {
  if (typeof props.addHandler === 'function') return props.addHandler()
  if (props.addTo) return router.push(props.addTo)
  emit('add')
}
</script>

<template>
  <div class="list-toolbar">
    <div class="toolbar toolbar--single" style="width:100%; justify-content: space-between;">
      <!-- 左侧：搜索框 -->
      <div class="cluster left" style="flex:1;" v-if="!props.hideSearch">
        <div class="input-group search-group" style="flex:1;">
          <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
          <input
            class="input"
            v-model="quick"
            placeholder="快速检索"
            @input="onQuickInput"
            @keydown.enter="triggerSearch"
          />
        </div>
      </div>
      <div class="cluster left" style="flex:1;" v-else></div>

      <!-- 右侧：Shuffle | 单图标视图切换 | 筛选 | 排序 -->
      <div class="cluster right">
        <slot v-if="props.showFieldManager" name="field-manager" />
        <el-tooltip v-if="!props.disableRandom" content="随机进入" placement="top" :show-after="120">
          <button class="icon-btn" :class="{ rolling }" title="随机进入" @click="onRandomClick">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 3h5v5"/><path d="M4 20l5-5 4 4 5-5"/><path d="M16 3l-4 4 5 5"/><path d="M3 16h5v5"/></svg>
          </button>
        </el-tooltip>

        <el-tooltip v-if="!props.disableAdd" content="新增" placement="top" :show-after="120">
          <button class="icon-btn" title="新增" aria-label="新增" @click="onAddClick">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
          </button>
        </el-tooltip>

        <el-tooltip v-if="!props.disableViewToggle" content="切换视图" placement="top" :show-after="120">
          <button class="icon-btn" title="切换视图" @click="cycleView">
            <svg v-if="localView==='card'" viewBox="0 0 24 24" aria-label="卡片视图"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></svg>
            <svg v-else-if="localView==='list'" viewBox="0 0 24 24" aria-label="列表视图"><path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/></svg>
            <svg v-else viewBox="0 0 24 24" aria-label="大图视图"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M8 13l3-3 5 6"/><circle cx="8.5" cy="9" r="1.5"/></svg>
          </button>
        </el-tooltip>

        <slot name="filter">
          <el-tooltip content="字段筛选" placement="top" :show-after="120">
            <button class="icon-btn" title="字段筛选" aria-label="字段筛选" @click="emit('open-filter')">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 4H8"/><circle cx="6" cy="4" r="2"/><path d="M21 12H6"/><circle cx="18" cy="12" r="2"/><path d="M21 20H8"/><circle cx="12" cy="20" r="2"/></svg>
            </button>
          </el-tooltip>
        </slot>

        <slot name="sort">
          <el-tooltip content="排序" placement="top" :show-after="120">
            <button class="icon-btn" title="排序" aria-label="排序" @click="emit('open-sort')">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 8l4-4 4 4"/><path d="M7 4v16"/><path d="M21 16l-4 4-4-4"/><path d="M17 4v16"/></svg>
            </button>
          </el-tooltip>
        </slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.list-toolbar { width: 100%; }
.toolbar--single {
  border-radius: var(--radius-lg);
  /* 主题适配：通过局部变量控制浅色/深色背景的品牌混合强度 */
  --toolbar-tint: 6%;
  background: color-mix(in oklab, var(--surface), var(--brand-weak) var(--toolbar-tint));
  box-shadow: none;
}
.left, .right { gap: var(--space-3); }
.left, .right { gap: var(--space-3); }

/* 搜索框：圆角 + 聚焦阴影与光晕 */
.search-group { min-width: 320px; }
.search-group:focus-within {
  box-shadow: var(--shadow-2);
  border-color: color-mix(in oklab, var(--brand), black 12%);
  animation: glow-in 180ms var(--ease);
}
@keyframes glow-in {
  0% { outline: 0px solid transparent; }
  100% { outline: 2px solid color-mix(in oklab, var(--brand), white 65%); }
}

/* 图标按钮：轻量、圆角、悬停高亮 */
.icon-btn {
  width: 34px;
  height: 34px;
  display: inline-grid;
  place-items: center;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  transition: background var(--duration-fast) var(--ease),
              transform var(--duration-fast) var(--ease),
              color var(--duration-fast) var(--ease);
}
.icon-btn:hover { background: color-mix(in oklab, var(--surface), var(--brand-weak) 14%); color: var(--text-primary); }

/* 掷骰子动画 */
.icon-btn.rolling { animation: dice-roll 420ms var(--ease); }
@keyframes dice-roll {
  0% { transform: rotate(0deg); }
  20% { transform: rotate(12deg) translateX(1px); }
  40% { transform: rotate(-10deg) translateX(-1px); }
  60% { transform: rotate(8deg) translateX(1px); }
  80% { transform: rotate(-6deg) translateX(-1px); }
  100% { transform: rotate(0deg); }
}

/* 图标统一为线性风格（lucide/remixicon） */
.icon-btn svg, .search-group .icon {
  width: 18px; height: 18px;
  stroke: currentColor; fill: none; stroke-width: 2;
  stroke-linecap: round; stroke-linejoin: round;
}

:slotted(.icon-btn) {
  width: 34px;
  height: 34px;
  display: inline-grid;
  place-items: center;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  transition: background var(--duration-fast) var(--ease),
              transform var(--duration-fast) var(--ease),
              color var(--duration-fast) var(--ease);
}
:slotted(.icon-btn:hover) { background: color-mix(in oklab, var(--surface), var(--brand-weak) 14%); color: var(--text-primary); }
:slotted(.icon-btn svg) { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

/* 主题适配：浅色降低透明度，深色略提高以保持层次 */
:global(html[data-theme="light"]) .toolbar--single { --toolbar-tint: 3%; }
:global(html[data-theme="dark"]) .toolbar--single { --toolbar-tint: 7%; }
</style>
