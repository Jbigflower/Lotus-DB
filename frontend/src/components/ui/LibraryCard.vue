<script setup lang="ts">
import { computed } from 'vue'
import type { LibraryRead } from '@/types/library'

export interface LibraryCardProps {
  id: string
  name?: string
  coverUrl?: string
  mediaCount?: number
  userName?: string
  userAvatarUrl?: string
  dense?: boolean
  library?: LibraryRead
}

const props = defineProps<LibraryCardProps>()

const emit = defineEmits<{
  (e: 'open', id: string): void
  (e: 'contextmenu', payload: { id: string; x: number; y: number; target: HTMLElement | null }): void
}>()

const finalId = computed(() => props.id ?? props.library?.id ?? '')
const finalName = computed(() => props.name ?? props.library?.name ?? '')
const finalCover = computed(() => props.coverUrl)
const finalCount = computed(() => props.mediaCount)
const finalUserName = computed(() => props.userName)
const finalUserAvatar = computed(() => props.userAvatarUrl)

function onOpen() { emit('open', finalId.value) }
function onContextMenu(e: MouseEvent) {
  const target = e.currentTarget as HTMLElement | null
  emit('contextmenu', { id: finalId.value, x: e.clientX, y: e.clientY, target })
}
</script>

<template>
  <article class="library-card" :class="{ dense: props.dense }" @click="onOpen" @contextmenu.prevent="onContextMenu">
    <div class="library-card__cover" :class="{ placeholder: !finalCover }" :style="finalCover ? { backgroundImage: `url('${finalCover}')` } : undefined">
      <!-- Bottom gradient overlay -->
      <div class="library-card__overlay">
        <div class="overlay__row">
          <h3 class="title">{{ finalName }}</h3>
          <div class="info">
            <span v-if="typeof finalCount === 'number'" class="count">媒体 {{ finalCount }}</span>
            <span class="user" v-if="finalUserName || finalUserAvatar">
              <img v-if="finalUserAvatar" :src="finalUserAvatar" alt="用户头像" class="avatar" />
              <span v-else class="avatar avatar--placeholder">{{ (finalUserName ?? '用户')[0] }}</span>
              <span class="user-name">{{ finalUserName ?? '匿名用户' }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.library-card {
  position: relative;
  width: 100%;
  color: var(--text-primary);
  transition: transform var(--duration-medium) var(--ease),
              box-shadow var(--duration-medium) var(--ease);
}
.library-card:hover { transform: scale(1.06); box-shadow: var(--shadow-2); z-index: 2; }

.library-card__cover {
  position: relative;
  aspect-ratio: 2 / 1;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: color-mix(in oklab, var(--surface-2), black 6%);
  background-size: cover;
  background-position: center;
  filter: brightness(0.85);
  transition: filter var(--duration-medium) var(--ease);
  box-shadow: var(--shadow-1);
}
.library-card:hover .library-card__cover { filter: brightness(1); }

.library-card__cover.placeholder {
  background-image: linear-gradient(135deg,
    color-mix(in oklab, var(--surface-2), var(--brand-weak) 14%),
    color-mix(in oklab, var(--surface-2), black 6%)
  );
}

.library-card__overlay {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  padding: var(--space-4);
  background: linear-gradient(to top, rgba(0,0,0,0.65), rgba(0,0,0,0.2) 55%, transparent 80%);
  color: #fff;
}
.overlay__row { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-3); }
.title { font-size: var(--text-xl); line-height: var(--line-tight); margin: 0; opacity: 0.85; transition: opacity var(--duration-medium) var(--ease); }
.library-card:hover .title { opacity: 1; }

.info { display: inline-flex; align-items: center; gap: 10px; }
.count { font-size: var(--text-sm); color: color-mix(in oklab, white, black 20%); }
.user { display: inline-flex; align-items: center; gap: 8px; }
.avatar { width: 28px; height: 28px; border-radius: var(--radius-pill); border: 1px solid rgba(255,255,255,0.35); box-shadow: var(--shadow-1); object-fit: cover; }
.avatar--placeholder { display: inline-grid; place-items: center; background: rgba(255,255,255,0.18); color: #fff; }
.user-name { font-size: var(--text-sm); color: #fff; }

.library-card.dense .library-card__overlay { padding: var(--space-3); }
.library-card.dense .title { font-size: var(--text-lg); }
</style>