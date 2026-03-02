<script setup lang="ts">
import { ref } from 'vue'
import MediaCard from '@/components/ui/MediaCard.vue'
import type { MediaCardProps } from '@/components/ui/MediaCard.vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const items = ref<MediaCardProps[]>([
  { id: 'tt0111161', title: 'The Shawshank Redemption', year: 1994, rating: 9.3, genres: ['Drama'], tags: ['经典', '励志'], poster: 'https://image.tmdb.org/t/p/w500/q6y0Go1tsGEsmtFryDOJo3dEmqu.jpg', progressPercent: 35, isFavorite: true },
  { id: 'tt0068646', title: 'The Godfather', year: 1972, rating: 9.2, genres: ['Crime','Drama'], tags: ['黑帮'], progressPercent: 0 },
  { id: 'tt0468569', title: 'The Dark Knight', year: 2008, rating: 9.0, genres: ['Action'], tags: ['蝙蝠侠','诺兰'], poster: 'https://image.tmdb.org/t/p/w500/qJ2tW6WMUDux911r6m7haRef0WH.jpg', progressPercent: 68, inWatchLater: true },
  { id: 'tt0109830', title: 'Forrest Gump', year: 1994, rating: 8.8, genres: ['Drama','Romance'], tags: ['人生'], progressPercent: 12 },
  { id: 'tt0137523', title: 'Fight Club', year: 1999, rating: 8.8, genres: ['Drama'], tags: ['反套路'], progressPercent: 0 },
  { id: 'tt0120737', title: 'The Lord of the Rings', year: 2001, rating: 8.8, genres: ['Fantasy','Adventure'], tags: ['中土世界'], progressPercent: 0 },
])

function onOpen(id: string | number) { router.push(`/movies/${id}`) }
function onPlay(id: string | number) { console.log('play', id) }
function onPreview(id: string | number) { console.log('preview', id) }
function onFav(id: string | number) {
  const item = items.value.find(x => x.id === id)
  if (!item) return
  item.isFavorite = !(item.isFavorite ?? false)
}
function onLater(id: string | number) {
  const item = items.value.find(x => x.id === id)
  if (!item) return
  item.inWatchLater = !(item.inWatchLater ?? false)
}
</script>

<template>
  <section class="content">
    <h2>MediaCard 演示</h2>
    <p class="text-muted">参考 Netflix 风格，悬停扩大并显示详情层。</p>
    <div class="demo-grid">
      <MediaCard
        v-for="m in items"
        :key="m.id"
        v-bind="m"
        @open="onOpen"
        @play="onPlay"
        @preview="onPreview"
        @toggle-favorite="onFav"
        @toggle-watch-later="onLater"
      />
    </div>
  </section>
</template>

<style scoped>
.demo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--gap);
  padding-block: var(--space-5);
}
</style>