<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useUserCollectionsStore } from '@/stores/user_collections'
import { useUsersStore } from '@/stores/users'
import { users as usersApi, movies as moviesApi } from '@/api'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SortSelect from '@/components/ui/SortSelect.vue'

// 路由参数：片单 ID
const route = useRoute()
const router = useRouter()
const playlistId = ref<string>('')
const userStore = useUserStore()
const collStore = useUserCollectionsStore()
const usersStore = useUsersStore()

// 视图状态：与库详情一致（含完整筛选与排序）
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

const coverMap = ref<Record<string, string>>({})
const items = computed(() => collStore.currentMovies.map((m: any) => ({ ...m, poster: coverMap.value[m.id] ?? undefined })))

async function loadPlaylist(id: string) {
  const token = userStore.token ?? ''
  if (!token || !id) { ElMessage.error('未登录'); return }
  try {
    await collStore.fetchById(token, id)
    await collStore.fetchMovies(token, id)
    const ids = (collStore.currentMovies ?? []).filter((m: any) => m?.has_poster === true).map((m: any) => m.id)
    if (ids.length > 0) {
      let urls: string[] = []
      try { urls = await moviesApi.getMovieCoversSigned(token, ids, 'poster.jpg') } catch {}
      const map: Record<string, string> = { ...coverMap.value }
      for (let i = 0; i < ids.length; i += 1) { const u = urls[i]; if (u) map[ids[i]] = u }
      coverMap.value = map
    }
  } catch { }
}

const ownerName = ref<string>('')
const ownerAvatarUrl = ref<string | null>(null)
const ownerAvatarError = ref<boolean>(false)
const ownerInitial = computed(() => (ownerName.value?.[0] ?? '?').toUpperCase())

async function loadOwner() {
  const token = userStore.token ?? ''
  const c = collStore.currentCollection
  if (!token || !c || !c.is_public) { ownerName.value = ''; ownerAvatarUrl.value = null; return }
  try {
    const ownerId = c.user_id
    if (ownerId) {
      const cached = usersStore.entities[ownerId]
      if (!cached) await usersStore.fetchById(token, ownerId)
      ownerName.value = usersStore.entities[ownerId]?.username ?? ''
      const urls = await usersApi.getUserProfilesSigned(token, [ownerId])
      ownerAvatarUrl.value = urls?.[0] ?? null
      ownerAvatarError.value = false
    }
  } catch {
    ownerAvatarUrl.value = null
    ownerAvatarError.value = true
  }
}

watch(() => route.params.id, (v) => {
  playlistId.value = String(v ?? '')
  loadPlaylist(playlistId.value)
}, { immediate: true })

watch(() => collStore.currentCollection?.id, async () => { await loadOwner() })

// 过滤
const filtered = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return items.value.filter(i => {
    if (!showDeleted.value && i.is_deleted) return false
    if (typeFilter.value !== 'all' && i.type !== typeFilter.value) return false
    if (q && !(`${i.title}`.toLowerCase()).includes(q)) return false
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

// 交互
function onRandom() {
  const arr = sorted.value
  if (!arr.length) return
  const pick = arr[Math.floor(Math.random() * arr.length)]
  console.log('随机进入媒体:', pick)
}
function onOpen(id: string | number) { router.push({ name: 'movie', params: { id } }) }
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
</script>

<template>
  <!-- 用户片单详情：继承布局与交互，动态加载指定片单内容 -->
  <section class="playlist-detail content mode-media" :data-playlist-id="playlistId">
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
      <p class="hint">片单筛选交互与库详情保持一致。</p>
    </div>

    <div v-if="collStore.currentCollection?.is_public" class="owner">
      <div class="avatar">
        <img v-if="ownerAvatarUrl && !ownerAvatarError" :src="ownerAvatarUrl" alt="" @error="ownerAvatarError = true" />
        <span v-else>{{ ownerInitial }}</span>
      </div>
      <div class="name" :title="ownerName">{{ ownerName }}</div>
    </div>

    <div v-if="showSort" class="panel panel--sort">
      <SortSelect :sort-by="'date'" :sort-order="sortOrder" @update:sortBy="mapSortBy" @update:sortOrder="updateSortOrder" />
    </div>

    <MediaGrid
      :items="paged"
      :dense="viewMode==='list'"
      @open="onOpen"
      @play="(id) => console.log('play', id)"
      @preview="(id) => console.log('preview', id)"
      @toggle-favorite="(id) => console.log('fav', id)"
      @toggle-watch-later="(id) => console.log('later', id)"
    />

    <footer class="page-footer">
      <PaginationBar :page="page" :pageSize="pageSize" :total="total" @prev="prevPage" @next="nextPage" />
    </footer>
  </section>
</template>

<style scoped>
.content { padding-block: var(--space-5); max-width: none; width: 100%; padding-inline: var(--content-pad); }
.playlist-detail { display: grid; gap: var(--space-4); }
.owner { display: inline-flex; align-items: center; gap: 10px; height: 36px; padding: 0 10px 0 8px; border-radius: var(--radius-pill); background: color-mix(in oklab, var(--surface-2), white 18%); border: 1px solid color-mix(in oklab, var(--border), white 10%); color: color-mix(in oklab, var(--text-primary), var(--text-muted) 35%); }
.owner .avatar { width: 32px; height: 32px; border-radius: 50%; overflow: hidden; background: color-mix(in oklab, var(--surface-2), black 5%); display: grid; place-items: center; color: var(--text-secondary); font-weight: 700; font-size: var(--text-sm); }
.owner .avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }
.owner .name { max-width: 140px; color: var(--text-primary); opacity: 0.9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; font-size: var(--text-sm); }
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
