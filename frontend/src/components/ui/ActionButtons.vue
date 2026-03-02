<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 isFavorite/isWatchLater；监听 @play/@preview/@toggle-favorite/@toggle-watch-later/@add-to-list。
 *
 * 设计思路：
 * - 将常见操作聚合为一组按钮，保证语义明确；状态由外部驱动。
 *
 * 页面表现（PlainText）：
 * - 一排操作按钮：播放、预播、收藏（带状态）、待看（带状态）、加入片单。
 */
const props = defineProps<{
  isFavorite?: boolean
  isWatchLater?: boolean
}>()

const emit = defineEmits<{
  (e: 'play'): void
  (e: 'complete'): void
  (e: 'toggle-favorite'): void
  (e: 'toggle-watch-later'): void
  (e: 'add-to-list'): void
}>()
</script>

<template>
  <div class="action-buttons" role="group" aria-label="常用操作">
    <el-tooltip content="播放" placement="top" :show-after="120">
      <button type="button" class="op-btn" @click="emit('play')" aria-label="播放">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7-11-7z"/></svg>
      </button>
    </el-tooltip>
    <el-tooltip content="完播" placement="top" :show-after="120">
      <button type="button" class="op-btn" @click="emit('complete')" aria-label="完播">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zm0 12a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z"/></svg>
      </button>
    </el-tooltip>
    <el-tooltip content="收藏" placement="top" :show-after="120">
      <button
        type="button"
        class="op-btn"
        :class="{ 'is-active': props.isFavorite === true }"
        @click="emit('toggle-favorite')"
        :aria-pressed="props.isFavorite"
        aria-label="收藏"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17.27L18.18 21 16.54 13.97 22 9.24l-7.19-.62L12 2 9.19 8.62 2 9.24l5.46 4.73L5.82 21z"/></svg>
      </button>
    </el-tooltip>
    <el-tooltip content="待观看" placement="top" :show-after="120">
      <button
        type="button"
        class="op-btn"
        :class="{ 'is-active': props.isWatchLater === true }"
        @click="emit('toggle-watch-later')"
        :aria-pressed="props.isWatchLater"
        aria-label="稍后观看"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8v5l4.3 2.58.7-1.16-3.5-2.09V8z"/><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/></svg>
      </button>
    </el-tooltip>
    <el-tooltip content="加入片单" placement="top" :show-after="120">
      <button type="button" class="op-btn op-btn--square" @click="emit('add-to-list')" aria-label="加入片单">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 13H5v-2h14v2zm-6 8H7a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h10a2 2 0 0 1 2 2v6h-2V5H7v14h6v2zm8-6v2h-2v2h-2v-2h-2v-2h2v-2h2v2h2z"/></svg>
      </button>
    </el-tooltip>
  </div>
</template>

<style scoped>
.action-buttons { display: inline-flex; gap: 12px; align-items: center; }
.op-btn { height: 40px; min-width: 40px; padding: 0 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface); color: var(--text-primary); opacity: 0.8; display: inline-grid; place-items: center; transition: opacity 200ms var(--ease), transform 160ms var(--ease), background-color 200ms var(--ease), border-color 200ms var(--ease); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.op-btn svg { width: 20px; height: 20px; fill: currentColor; }
.op-btn:hover { opacity: 1; }
.op-btn:active { transform: translateY(1px); opacity: 0.96; }
.op-btn:focus-visible { outline: 2px solid color-mix(in oklab, var(--brand), white 40%); outline-offset: 2px; }
.op-btn--square { width: 40px; padding: 0; }

/* 激活态：收藏/待观看为 true 时的视觉强化 */
.op-btn.is-active,
.op-btn[aria-pressed="true"] {
  background: color-mix(in oklab, var(--surface), var(--brand-weak) 16%);
  border-color: color-mix(in oklab, var(--border), var(--brand) 32%);
  color: color-mix(in oklab, var(--text-primary), var(--brand) 30%);
  opacity: 1;
}

@media (prefers-color-scheme: dark) {
  .op-btn { background: color-mix(in oklab, var(--surface), var(--brand-weak) 8%); border-color: color-mix(in oklab, var(--border), var(--brand) 22%); }
  .op-btn:hover { background: color-mix(in oklab, var(--surface), var(--brand-weak) 16%); }
}
</style>