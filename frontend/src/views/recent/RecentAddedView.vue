<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useMovieStore } from '@/stores/movie'

// 视图状态：搜索、视图模式、排序（仅日期方向）
const searchQuery = ref('')
const viewMode = ref<'card' | 'list' | 'gallery'>('card')
const sortOrder = ref<'asc' | 'desc'>('desc')

// 分页（本地分页以便演示；后续可接入后端分页）
const page = ref(1)
const pageSize = ref(24)
const userStore = useUserStore()
const movieStore = useMovieStore()

// Demo 数据：最近添加的媒体条目（统一使用 created_at 作为排序依据）
type DemoItem = {
  id: string | number
  title: string
  rating?: number
  tags?: string[]
  poster?: string
  type: 'movie' | 'tv'
  created_at?: string
}
const items = computed(() => movieStore.list)

// 过滤（仅支持搜索关键字；不支持筛选条件）
const filtered = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return items.value.filter(i => {
    if (q && !(`${i.title}`.toLowerCase()).includes(q)) return false
    return true
  })
})

// 排序（仅支持按添加日期 created_at；方向可选）
const sorted = computed(() => {
  const base = [...filtered.value]
  const dir = sortOrder.value === 'asc' ? 1 : -1
  base.sort((a, b) => {
    const av = a.created_at
    const bv = b.created_at
    if (av == null && bv == null) return 0
    if (av == null) return -1 * dir
    if (bv == null) return 1 * dir
    const aTime = /\d{4}-\d{2}-\d{2}/.test(av) ? Date.parse(av) : 0
    const bTime = /\d{4}-\d{2}-\d{2}/.test(bv) ? Date.parse(bv) : 0
    if (aTime < bTime) return -1 * dir
    if (aTime > bTime) return 1 * dir
    return 0
  })
  return base
})

// 分页切片
const total = computed(() => sorted.value.length)
const rangeStart = computed(() => (total.value ? (page.value - 1) * pageSize.value + 1 : 0))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
const paged = computed(() => sorted.value.slice((page.value - 1) * pageSize.value, (page.value) * pageSize.value))

// 交互回调（透传自 ListToolbar 与 PaginationBar）
function onRandom() {
  const arr = sorted.value
  if (!arr.length) return
  const pick = arr[Math.floor(Math.random() * arr.length)]
  console.log('随机进入媒体:', pick)
}
function onToggleView(mode: 'card' | 'list' | 'gallery') { viewMode.value = mode }
function onOpenSort() { showSort.value = !showSort.value }
function onSearch(q: string) { searchQuery.value = q; page.value = 1 }

// 排序面板开关（无筛选面板）
const showSort = ref(false)


// 分页事件
function prevPage() { if (page.value > 1) page.value -= 1 }
function nextPage() {
  const pageCount = Math.ceil(total.value / pageSize.value)
  if (page.value < pageCount) page.value += 1
}

onMounted(async () => {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await movieStore.fetchRecent(token, { size: 24 }) } catch { }
})
</script>

<template>
  <!-- 最近添加：与库详情页一致的列表结构，但无筛选、仅日期排序 -->
  <section class="recent-added content mode-media">
    <!-- 顶部：列表工具栏（单行图标化） -->
    <ListToolbar
      :total="total"
      :range-start="rangeStart"
      :range-end="rangeEnd"
      :view-mode="viewMode"
      @random="onRandom"
      @toggle-view="onToggleView"
      @open-sort="onOpenSort"
      @search="onSearch"
    >
      <!-- 不支持筛选：移除筛选按钮 -->
      <template #filter></template>
    </ListToolbar>

    <!-- 排序面板：仅方向（固定按 created_at） -->
    <div v-if="showSort" class="panel panel--sort">
      <div class="row">
        <span>排序方向：</span>
        <label class="seg"><input type="radio" value="desc" v-model="sortOrder"> 最新在前</label>
        <label class="seg"><input type="radio" value="asc" v-model="sortOrder"> 最旧在前</label>
      </div>
      <p class="hint">仅按“添加日期”排序。</p>
    </div>

    <!-- 中部：媒体网格（响应搜索/排序变化） -->
    <MediaGrid
      :items="paged"
      :dense="viewMode==='list'"
      :projector="(raw: any) => { const id=String(raw?.id ?? ''); const ent=movieStore.entities[id]; return { id, title: raw.title, poster: raw.poster, rating: raw.rating, tags: raw.tags, isFavorite: ent?.is_favoriter===true, inWatchLater: ent?.is_watchLater===true } }"
      @open="(id) => console.log('open', id)"
      @play="(id) => console.log('play', id)"
      @preview="(id) => console.log('preview', id)"
      @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
      @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
    />

    <!-- 底部：分页导航（浅色主题降低透明度） -->
    <footer class="page-footer">
      <PaginationBar :page="page" :pageSize="pageSize" :total="total" @prev="prevPage" @next="nextPage" />
    </footer>
  </section>
</template>

<style scoped>
.content { padding-block: var(--space-5); max-width: none; width: 100%; padding-inline: var(--content-pad); }
.recent-added { display: grid; gap: var(--space-4); }

/* 排序面板：轻量下拉（保持与网格合理间距） */
.panel { border: 1px solid var(--border); background: color-mix(in oklab, var(--surface), var(--brand-weak) 4%); border-radius: var(--radius-lg); padding: var(--space-3); }
.panel--sort { margin-top: -4px; }
.row { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.seg { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); }
.hint { margin-top: var(--space-2); color: var(--text-muted); font-size: var(--text-sm); }

/* 底部分页包裹：浅色主题降低透明度，深色略提升对比 */
.page-footer { display: flex; justify-content: center; }
:global(html[data-theme="light"]) .page-footer { opacity: 0.9; }
:global(html[data-theme="dark"]) .page-footer { opacity: 1; }
</style>
