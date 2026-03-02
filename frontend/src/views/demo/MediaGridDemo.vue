<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import type { MediaCardProps } from '@/components/ui/MediaCard.vue'

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

// 工具栏交互（示例）
const viewMode = ref<'card' | 'list' | 'gallery'>('card')
function onRandom() {
  const len = items.value.length
  if (!len) return
  const idx = Math.floor(Math.random() * len)
  const item = items.value[idx]
  if (!item) return
  const id = item.id
  router.push(`/movies/${id}`)
}
function onToggleView(mode: 'card' | 'list' | 'gallery') { viewMode.value = mode }
function onOpenSort() { console.log('open sort settings') }
function onOpenFilter() { console.log('open filter panel') }
const q = ref('')
function onSearch(v: string) { q.value = v }

const filtered = computed(() => {
  const keyword = q.value.trim()
  if (!keyword) return items.value
  return items.value.filter(m =>
    (m.title?.toLowerCase().includes(keyword.toLowerCase())) ||
    (m.tags?.some(t => t.toLowerCase().includes(keyword.toLowerCase())))
  )
})

// 根据视图模式调整 MediaGrid 的最小列宽，模拟“大图视图”
const gridVars = computed(() => {
  if (viewMode.value === 'gallery') {
    return { '--card-min-width': '300px' }
  }
  return { '--card-min-width': '220px' }
})
</script>

<template>
  <section class="content">
    <h2>MediaGrid 演示</h2>
    <p class="text-muted">使用 MediaGrid 批量渲染 MediaCard，并透传交互事件。</p>

    <!-- 列表页工具栏：两行布局，放在网格上方 -->
    <ListToolbar
      :total="items.length"
      :range-start="filtered.length ? 1 : 0"
      :range-end="filtered.length"
      :view-mode="viewMode"
      @random="onRandom"
      @toggle-view="onToggleView"
      @open-sort="onOpenSort"
      @open-filter="onOpenFilter"
      @search="onSearch"
    />

    <MediaGrid
      :items="filtered"
      :dense="viewMode==='list'"
      :style="gridVars"
      @open="onOpen"
      @play="onPlay"
      @preview="onPreview"
      @toggle-favorite="onFav"
      @toggle-watch-later="onLater"
    />
  </section>
</template>

<style scoped>
.content { padding-block: var(--space-5); }
</style>