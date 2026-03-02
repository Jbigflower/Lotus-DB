<script setup lang="ts">
import { computed } from 'vue'
import type { MovieRead } from '@/types/movie'

export interface MediaCardProps {
  id: string | number
  title?: string
  poster?: string
  year?: number
  rating?: number
  genres?: string[]
  tags?: string[]
  progressPercent?: number
  showProgress?: boolean
  isFavorite?: boolean
  inWatchLater?: boolean
  dense?: boolean
  movie?: MovieRead
}

const props = defineProps<MediaCardProps>()

const emit = defineEmits<{
  (e: 'open', id: string | number): void
  (e: 'play', id: string | number): void
  (e: 'preview', id: string | number): void
  (e: 'toggle-favorite', id: string | number): void
  (e: 'toggle-watch-later', id: string | number): void
  (e: 'contextmenu', payload: { id: string; x: number; y: number }): void
}>()

const finalId = computed(() => props.id ?? props.movie?.id ?? '')
const finalTitle = computed(() => props.title ?? props.movie?.title_cn ?? props.movie?.title ?? '')
const finalYear = computed(() => {
  if (typeof props.year === 'number') return props.year
  const d = props.movie?.release_date
  if (d && /^\d{4}/.test(d)) return parseInt(d.slice(0, 4))
  return undefined
})
const finalRating = computed(() => {
  const r = props.rating ?? props.movie?.rating ?? undefined
  return typeof r === 'number' ? r : undefined
})
const finalTags = computed(() => props.tags ?? props.movie?.tags ?? [])
const finalGenres = computed(() => props.genres ?? props.movie?.genres ?? [])
const progress = computed(() => Math.max(0, Math.min(100, props.progressPercent ?? 0)))
const showProgress = computed(() => props.showProgress !== false)

function onOpen() { emit('open', finalId.value) }
function onPreview() { emit('preview', finalId.value) }
function onPlay() { emit('play', finalId.value) }
let favTimer: number | undefined
let watchTimer: number | undefined
function onToggleFavorite() {
  if (favTimer) window.clearTimeout(favTimer)
  favTimer = window.setTimeout(() => { emit('toggle-favorite', finalId.value) }, 300)
}
function onToggleWatchLater() {
  if (watchTimer) window.clearTimeout(watchTimer)
  watchTimer = window.setTimeout(() => { emit('toggle-watch-later', finalId.value) }, 300)
}

function onContextMenu(e: MouseEvent) {
  const id = String(finalId.value)
  emit('contextmenu', { id, x: e.clientX, y: e.clientY })
}
</script>

<template>
  <article class="media-card" :class="{ dense: props.dense }" @click="onOpen" @contextmenu.prevent="onContextMenu">
    <!-- Poster area: 16:9 -->
    <div class="media-card__poster" :class="{ placeholder: !props.poster }" :style="props.poster ? { backgroundImage: `url('${props.poster}')` } : undefined">
      <!-- Action buttons -->
      <div class="media-card__actions" @click.stop>
        <button class="icon-btn" :class="{ active: props.isFavorite }" @click="onToggleFavorite" title="收藏">★</button>
        <button class="icon-btn" :class="{ active: props.inWatchLater }" @click="onToggleWatchLater" title="稍后观看">⏱</button>
      </div>

      <!-- Hover overlay details (delayed 200ms) -->
      <div class="media-card__overlay" @click.stop>
        <h4 class="title">{{ finalTitle }}</h4>
        <div class="meta">
          <span v-if="finalYear">{{ finalYear }}</span>
          <span v-if="finalRating !== undefined">评分 {{ finalRating }}</span>
        </div>
        <div v-if="finalGenres?.length" class="chips">
          <span v-for="g in finalGenres" :key="g" class="chip">{{ g }}</span>
        </div>
        <div v-if="finalTags?.length" class="chips wrap">
          <span v-for="t in finalTags" :key="t" class="chip">#{{ t }}</span>
        </div>
        <div class="overlay-actions">
          <button type="button" class="btn btn--primary btn--sm" @click="onPlay">播放</button>
          <button type="button" class="btn btn--ghost btn--sm" @click="onPreview">预览</button>
        </div>
      </div>

      <!-- Progress bar (fade in on hover) -->
      <div v-if="showProgress" class="media-card__progress">
        <div class="bar" :style="{ width: progress + '%' }" />
      </div>
    </div>

    <!-- Title under poster (default) -->
    <div class="media-card__caption">
      <div class="caption__title text-ellipsis">{{ finalTitle }}</div>
    </div>
  </article>
</template>

<style scoped>
.media-card {
  position: relative;
  display: grid;
  gap: 8px;
  width: 100%;
  color: var(--text-primary);
  transition: transform var(--duration-medium) var(--ease),
              box-shadow var(--duration-medium) var(--ease);
}
.media-card:hover { transform: scale(1.1); box-shadow: var(--shadow-2); z-index: 2; }
.media-card.dense { gap: 6px; }

.media-card__poster {
  position: relative;
  width: 100%;
  min-width: 0;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: color-mix(in oklab, var(--surface-2), black 6%);
  background-size: cover;
  background-position: center;
  box-shadow: var(--shadow-1);
}
.media-card__poster.placeholder {
  background-image: linear-gradient(135deg,
    color-mix(in oklab, var(--surface-2), var(--brand-weak) 14%),
    color-mix(in oklab, var(--surface-2), black 6%)
  );
}

.media-card__actions {
  position: absolute; top: 8px; right: 8px;
  display: inline-flex; gap: 6px;
  z-index: 2;
}
.icon-btn {
  height: 30px; width: 30px;
  display: inline-grid; place-items: center;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: color-mix(in oklab, var(--surface), var(--brand-weak) 10%);
  color: var(--text-secondary);
  cursor: pointer;
  transition: transform var(--duration-fast) var(--ease),
              background var(--duration-fast) var(--ease);
}
.icon-btn:hover { transform: scale(1.08); }
.icon-btn.active { background: var(--brand); color: var(--on-brand); border-color: transparent; }

.media-card__overlay {
  position: absolute; inset: 0; padding: 10px;
  display: grid; align-content: end; gap: 8px;
  background: linear-gradient(
    to top,
    color-mix(in oklab, var(--surface-3), transparent 35%),
    color-mix(in oklab, var(--surface-3), transparent 80%) 50%,
    transparent 75%
  );
  color: var(--text-on-surface);
  opacity: 0; pointer-events: none;
  transition: opacity var(--duration-medium) var(--ease);
  z-index: 1;
}
.media-card:hover .media-card__overlay { opacity: 1; transition-delay: 200ms; }

.title { font-size: var(--text-lg); line-height: var(--line-tight); margin: 0; }
.meta { display: inline-flex; align-items: center; gap: 10px; color: var(--text-secondary); font-size: var(--text-sm); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { background: color-mix(in oklab, var(--surface-2), var(--brand-weak) 12%); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-pill); padding: 2px 8px; font-size: var(--text-xs); }
.overlay-actions { display: inline-flex; gap: 8px; }

.media-card__progress { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: var(--surface-2); opacity: 0; transition: opacity var(--duration-medium) var(--ease); }
.media-card__progress .bar { height: 100%; background: var(--brand); }
.media-card:hover .media-card__progress { opacity: 1; }

.media-card__caption { padding: 0 4px; min-width: 0; }
.caption__title { font-size: var(--text-sm); }
</style>
