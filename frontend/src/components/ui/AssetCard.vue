<script setup lang="ts">
import { computed } from 'vue'
import type { AssetRead } from '@/types/asset'

export interface AssetCardProps {
  id: string | number
  assetTitle?: string
  movieTitle?: string
  movieId?: string | number
  thumbnailUrl?: string
  lastWatchedAt?: string
  progressPercent?: number
  showProgress?: boolean
  dense?: boolean
  asset?: AssetRead
}

const props = defineProps<AssetCardProps>()

const emit = defineEmits<{
  (e: 'open', id: string | number): void
  (e: 'play', id: string | number): void
  (e: 'click-movie', movieId: string | number): void
  (e: 'contextmenu', payload: { id: string; x: number; y: number }): void
}>()

const finalId = computed(() => props.id ?? props.asset?.id ?? '')
const finalTitle = computed(() => props.assetTitle ?? props.asset?.name ?? '')
const finalMovieTitle = computed(() => props.movieTitle ?? '')
const poster = computed(() => props.thumbnailUrl ?? '')
const progress = computed(() => Math.max(0, Math.min(100, props.progressPercent ?? 0)))
const showProgress = computed(() => props.showProgress !== false)

const formattedTime = computed(() => {
  if (!props.lastWatchedAt) return ''
  try {
    const date = new Date(props.lastWatchedAt)
    // Display format: 2/11 09:24
    return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return props.lastWatchedAt
  }
})

// Kept for MediaGrid compatibility, but internal clicks are specific
function onOpen() { emit('open', finalId.value) }

function onPlay() { emit('play', finalId.value) }

function onMovieClick() {
  if (props.movieId) {
    emit('click-movie', props.movieId)
  }
}

function onContextMenu(e: MouseEvent) {
  const id = String(finalId.value)
  emit('contextmenu', { id, x: e.clientX, y: e.clientY })
}
</script>

<template>
  <article class="asset-card" :class="{ dense: props.dense }" @contextmenu.prevent="onContextMenu">
    <!-- Poster Section -->
    <div class="asset-card__poster" :class="{ placeholder: !poster }" 
         :style="poster ? { backgroundImage: `url('${poster}')` } : undefined"
         @click.stop="onPlay">
      
      <!-- Overlay with Play Button -->
      <div class="poster-overlay">
        <div class="play-btn-circle">
          <svg viewBox="0 0 24 24" fill="currentColor" class="play-icon"><path d="M8 5v14l11-7z"/></svg>
        </div>
      </div>

      <!-- Progress Bar (Always Visible) -->
      <div v-if="showProgress" class="progress-track">
        <div class="progress-fill" :style="{ width: progress + '%' }" />
      </div>
    </div>

    <!-- Content Section -->
    <div class="asset-card__content">
      <!-- Media Title (Click -> Detail) -->
      <div v-if="finalMovieTitle" class="media-title text-ellipsis" @click.stop="onMovieClick" :title="finalMovieTitle">
        {{ finalMovieTitle }}
      </div>
      
      <!-- Asset Title (Click -> Play) -->
      <div class="asset-title text-ellipsis" @click.stop="onPlay" :title="finalTitle">
        {{ finalTitle }}
      </div>

      <!-- Meta Info -->
      <div class="meta-row">
        <span class="progress-text" v-if="showProgress && progress > 0">播放至 {{ Math.round(progress) }}%</span>
        <span class="separator" v-if="showProgress && progress > 0 && formattedTime">·</span>
        <span class="time" v-if="formattedTime">{{ formattedTime }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.asset-card {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-primary);
  transition: transform 0.2s ease;
}

/* Poster */
.asset-card__poster {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: color-mix(in oklab, var(--surface-2), black 6%);
  background-size: cover;
  background-position: center;
  cursor: pointer;
  box-shadow: var(--shadow-1);
}

.asset-card__poster.placeholder {
  background-image: linear-gradient(135deg, var(--surface-3), var(--surface-1));
}

/* Poster Overlay & Play Button */
.poster-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  opacity: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.2s ease;
}

.asset-card__poster:hover .poster-overlay {
  opacity: 1;
}

.play-btn-circle {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  transform: scale(0.9);
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  border: 1px solid rgba(255,255,255,0.2);
}

.asset-card__poster:hover .play-btn-circle {
  transform: scale(1);
}

.play-icon {
  width: 24px;
  height: 24px;
  margin-left: 2px; /* Visual adjustment */
}

/* Progress Bar */
.progress-track {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: rgba(255, 255, 255, 0.2);
}

.progress-fill {
  height: 100%;
  background: var(--brand); 
  border-top-right-radius: 2px;
  border-bottom-right-radius: 2px;
}

/* Content */
.asset-card__content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 2px;
  min-width: 0; /* Crucial for text-ellipsis to work in flex children */
  overflow: hidden;
}

.media-title {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  cursor: pointer;
  transition: color 0.2s;
  width: fit-content;
}

.media-title:hover {
  color: var(--brand);
  text-decoration: underline;
}

.asset-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
  cursor: pointer;
  transition: color 0.2s;
}

.asset-title:hover {
  color: var(--brand);
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.text-ellipsis {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
