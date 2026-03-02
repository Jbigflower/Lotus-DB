<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useUserCollectionsStore } from '@/stores/user_collections'
import { CustomListType } from '@/types/user_collection'
import { useMovieStore } from '@/stores/movie'
import { movies as moviesApi } from '@/api'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SortSelect from '@/components/ui/SortSelect.vue'

// 视图状态
const searchQuery = ref('')
const viewMode = ref<'card' | 'list' | 'gallery'>('card')
type SortKey = 'updated_at' | 'created_at' | 'title' | 'rating' | 'type'
const sortBy = ref<SortKey>('updated_at')
const sortOrder = ref<'asc' | 'desc'>('desc')

const onlyMe = ref<boolean>(false)
const onlyActive = ref<boolean>(false)
const typeFilter = ref<'all' | 'movie' | 'tv'>('all')
const showDeleted = ref<boolean>(false)

// 分页
const page = ref(1)
const pageSize = ref(24)

const userStore = useUserStore()
const collStore = useUserCollectionsStore()
const currentListId = ref<string | null>(null)
const items = computed(() => (currentListId.value ? (collStore.moviesById[currentListId.value] ?? []) : []))

// 过滤
const filtered = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return items.value.filter((i: any) => {
    if (!showDeleted.value && i.is_deleted) return false
    if (typeFilter.value !== 'all' && (i as any).type && (i as any).type !== typeFilter.value) return false
    const t = String((i as any).title ?? '')
    if (q && !t.toLowerCase().includes(q)) return false
    return true
  })
})

// 排序
const sorted = computed(() => {
  const base = [...filtered.value]
  const key = sortBy.value
  const dir = sortOrder.value === 'asc' ? 1 : -1
  base.sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (av == null && bv == null) return 0
    if (av == null) return -1 * dir
    if (bv == null) return 1 * dir
    const aTime = typeof av === 'string' && /\d{4}-\d{2}-\d{2}/.test(av) ? Date.parse(av) : av as number
    const bTime = typeof bv === 'string' && /\d{4}-\d{2}-\d{2}/.test(bv) ? Date.parse(bv) : bv as number
    if (aTime < bTime) return -1 * dir
    if (aTime > bTime) return 1 * dir
    return 0
  })
  return base
})

// 分页
const total = computed(() => sorted.value.length)
const rangeStart = computed(() => (total.value ? (page.value - 1) * pageSize.value + 1 : 0))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
const paged = computed(() => sorted.value.slice((page.value - 1) * pageSize.value, (page.value) * pageSize.value))

// 海报加载
const posterMap = ref<Record<string, string>>({})
async function refreshPosters() {
  const token = userStore.token ?? ''
  if (!token) return
  const ids = paged.value.map((m: any) => String(m.id))
  if (!ids.length) return
  try {
    const urls = await moviesApi.getMovieCoversSigned(token, ids, 'poster.jpg')
    const map: Record<string, string> = {}
    ids.forEach((id, i) => { map[id] = urls[i] ?? '' })
    posterMap.value = { ...posterMap.value, ...map }
  } catch {}
}
watch(paged, () => { refreshPosters() }, { immediate: true })

// 交互
function onRandom() {
  const arr = sorted.value
  if (!arr.length) return
  const pick = arr[Math.floor(Math.random() * arr.length)]
  console.log('随机进入媒体:', pick)
}
function onToggleView(mode: 'card' | 'list' | 'gallery') { viewMode.value = mode }
function onOpenSort() { showSort.value = !showSort.value }
function onOpenFilter() { showFilter.value = !showFilter.value }
function onSearch(q: string) { searchQuery.value = q; page.value = 1 }

// 面板开关
const showFilter = ref(false)
const showSort = ref(false)

function mapSortBy(v: string) {
  switch (v) {
    case 'date': sortBy.value = 'updated_at'; break
    case 'title': sortBy.value = 'title'; break
    case 'rating': sortBy.value = 'rating'; break
    default: sortBy.value = 'updated_at'
  }
}
function updateSortOrder(v: string) { sortOrder.value = v === 'asc' ? 'asc' : 'desc' }

// 分页
function prevPage() { if (page.value > 1) page.value -= 1 }
function nextPage() {
  const pageCount = Math.ceil(total.value / pageSize.value)
  if (page.value < pageCount) page.value += 1
}

const movieStore = useMovieStore()
const router = useRouter()

function openMovie(id: string | number) { router.push(`/movies/${id}`) }
function openPlayer(id: string | number) { router.push(`/player/${id}`) }

onMounted(async () => {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try {
    const res = await collStore.fetchList(token, CustomListType.FAVORITE)
    const uid = userStore.user?.id ?? null
    const target = (res.items ?? []).find((c: any) => c.type === CustomListType.FAVORITE && (!uid || c.user_id === uid))
    const id = target?.id
    if (id) { currentListId.value = id; await collStore.fetchMovies(token, id) }
    else { ElMessage.error('未找到当前用户的收藏片单') }
  } catch { ElMessage.error('加载收藏片单失败') }
})
</script>

<template>
  <!-- 收藏夹：复用稍后看页实现与交互 -->
  <section class="favorites content mode-media">
    <ListToolbar
      :total="total"
      :range-start="rangeStart"
      :range-end="rangeEnd"
      :view-mode="viewMode"
      @random="onRandom"
      @toggle-view="onToggleView"
      @open-sort="onOpenSort"
      @open-filter="onOpenFilter"
      @search="onSearch"
    />

    <div v-if="showFilter" class="panel panel--filter">
      <div class="row">
        <label class="cb"><input type="checkbox" v-model="onlyMe"> 只显示我的</label>
        <label class="cb"><input type="checkbox" v-model="onlyActive"> 只显示激活的</label>
        <label class="cb"><input type="checkbox" v-model="showDeleted"> 显示已删除</label>
      </div>
      <div class="row">
        <span>类型：</span>
        <label class="seg"><input type="radio" value="all" v-model="typeFilter"> 全部</label>
        <label class="seg"><input type="radio" value="movie" v-model="typeFilter"> 电影</label>
        <label class="seg"><input type="radio" value="tv" v-model="typeFilter"> 剧集</label>
      </div>
      <p class="hint">收藏夹筛选与交互保持与库详情一致。</p>
    </div>

    <div v-if="showSort" class="panel panel--sort">
      <SortSelect :sort-by="'date'" :sort-order="sortOrder" @update:sortBy="mapSortBy" @update:sortOrder="updateSortOrder" />
    </div>

    <MediaGrid
      :items="paged"
      :dense="viewMode==='list'"
      :projector="(raw: any) => { const id=String(raw?.id ?? ''); const ent=movieStore.entities[id]; return { id, title: raw.title, poster: posterMap[id] || raw.poster, rating: raw.rating, tags: raw.tags, isFavorite: (raw?.is_favoriter===true) || (ent?.is_favoriter===true), inWatchLater: (raw?.is_watchLater===true) || (ent?.is_watchLater===true) } }"
      @open="openMovie"
      @play="openPlayer"
      @preview="(id) => void 0"
      @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
      @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
    />

    <footer class="page-footer">
      <PaginationBar :page="page" :pageSize="pageSize" :total="total" @prev="prevPage" @next="nextPage" />
    </footer>
  </section>
</template>

<style scoped>
.content { padding-block: var(--space-5); max-width: none; width: 100%; padding-inline: var(--content-pad); }
.favorites { display: grid; gap: var(--space-4); }
.panel { border: 1px solid var(--border); background: color-mix(in oklab, var(--surface), var(--brand-weak) 4%); border-radius: var(--radius-lg); padding: var(--space-3); }
.panel--filter, .panel--sort { margin-top: -4px; }
.row { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.cb { display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); }
.seg { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); }
.hint { margin-top: var(--space-2); color: var(--text-muted); font-size: var(--text-sm); }
.page-footer { display: flex; justify-content: center; }
:global(html[data-theme="light"]) .page-footer { opacity: 0.9; }
:global(html[data-theme="dark"]) .page-footer { opacity: 1; }
</style>
