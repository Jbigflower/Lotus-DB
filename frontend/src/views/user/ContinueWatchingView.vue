<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import AssetCard from '@/components/ui/AssetCard.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import { useUserStore } from '@/stores/user'
import { useWatchHistoryStore } from '@/stores/watch_history'
import { useMovieStore } from '@/stores/movie'
import { movies, movieAssets } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const searchQuery = ref('')
const viewMode = ref<'card' | 'list' | 'gallery'>('card')
const sortOrder = ref<'asc' | 'desc'>('desc')
const page = ref(1)
const pageSize = ref(24)
const showSort = ref(false)
const showFilter = ref(false)
const includeCompleted = ref(false)

const userStore = useUserStore()
const watchStore = useWatchHistoryStore()
const movieStore = useMovieStore()
const router = useRouter()

const movieMap = ref<Record<string, any>>({})
const assetMap = ref<Record<string, any>>({})
const thumbMap = ref<Record<string, string>>({})

const contextMenu = ref({ visible: false, x: 0, y: 0, itemId: '' })
const detailsVisible = ref(false)
const detailsData = ref<any>(null)

async function loadData() {
  const token = userStore.token ?? ''
  if (!token) return
  const completed = includeCompleted.value ? undefined : false
  await watchStore.fetchList(token, { page: page.value, size: pageSize.value, completed })
  const movieIds = Array.from(new Set(watchStore.list.map(i => i.movie_id).filter(Boolean))) as string[]
  const assetIds = Array.from(new Set(watchStore.list.map(i => i.asset_id).filter(Boolean))) as string[]
  if (movieIds.length) {
    for (const id of movieIds) {
      const cached = movieStore.$state.entities?.[id]
      if (cached) { movieMap.value[id] = cached; continue }
      try { movieMap.value[id] = await movies.getMovie(token, id) } catch {}
    }
  }
  if (assetIds.length) {
    try {
      const thumbs = await movieAssets.getAssetThumbnailsSigned(token, assetIds)
      const tmap: Record<string, string> = {}
      for (let i = 0; i < assetIds.length; i++) {
        const u = thumbs[i]
        const aid = assetIds[i]
        if (u && aid) tmap[aid] = u
      }
      thumbMap.value = { ...thumbMap.value, ...tmap }
    } catch {}
    for (const aid of assetIds) {
      try { assetMap.value[aid] = await movieAssets.getMovieAsset(token, aid) } catch {}
    }
  }
}

const sorted = computed(() => {
  const base = [...watchStore.sortedList]
  return sortOrder.value === 'asc' ? base.reverse() : base
})

const gridItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  const arr = sorted.value.map(i => {
    const m = i.movie_id ? movieMap.value[i.movie_id] : null
    const a = i.asset_id ? assetMap.value[i.asset_id] : null
    const movieTitle = m?.title_cn ?? m?.title ?? ''
    const assetTitle = a?.name ?? undefined
    const progress = (i.total_duration ?? 0) > 0 ? (i.last_position / (i.total_duration ?? 1)) * 100 : 0
    return {
      id: `${i.movie_id ?? ''}|${i.asset_id ?? ''}`,
      assetTitle,
      movieTitle,
      thumbnailUrl: i.asset_id ? thumbMap.value[i.asset_id] : undefined,
      lastWatchedAt: i.last_watched ?? undefined,
      progressPercent: progress,
    }
  })
  return q ? arr.filter(x => String(x.movieTitle ?? x.assetTitle ?? '').toLowerCase().includes(q)) : arr
})

const projectAsset = (raw: any) => raw

const total = computed(() => watchStore.listMeta.total)
const rangeStart = computed(() => (total.value ? (page.value - 1) * pageSize.value + 1 : 0))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))

function onRandom() {
  const pick = watchStore.randomItem
  if (!pick || !pick.movie_id) return
  router.push(`/player/${pick.movie_id}`)
}
function onToggleView(mode: 'card' | 'list' | 'gallery') { viewMode.value = mode }
function onOpenSort() { showSort.value = !showSort.value }
function onOpenFilter() { showFilter.value = !showFilter.value }
function onSearch(q: string) { searchQuery.value = q; page.value = 1 }
function onToggleIncludeCompleted() { page.value = 1; loadData() }
function openAsset(id: string | number) {
  const val = String(id)
  const [movieId, assetId] = val.split('|')
  if (!movieId || !assetId) return
  router.push({ path: `/player/${movieId}`, query: { asset_id: assetId } })
}

function prevPage() { if (page.value > 1) { page.value -= 1; loadData() } }
function nextPage() {
  const pageCount = Math.ceil((total.value ?? 0) / pageSize.value)
  if (page.value < pageCount) { page.value += 1; loadData() }
}

function onContextMenu(payload: { id: string, x: number, y: number }) {
  contextMenu.value = { visible: true, x: payload.x, y: payload.y, itemId: payload.id }
}

function closeMenu() {
  contextMenu.value.visible = false
}

function getWatchHistoryByItemId(itemId: string) {
  const [mid, aid] = itemId.split('|')
  return watchStore.list.find(i => 
    String(i.movie_id ?? '') === mid && 
    String(i.asset_id ?? '') === aid
  )
}

async function onDeleteHistory() {
  const item = getWatchHistoryByItemId(contextMenu.value.itemId)
  if (!item) return
  
  try {
    await ElMessageBox.confirm('确定要删除这条播放记录吗？此操作不可恢复。', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await watchStore.deleteItems(userStore.token ?? '', [item.id])
    ElMessage.success('删除成功')
    closeMenu()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

function onShowDetails() {
  const item = getWatchHistoryByItemId(contextMenu.value.itemId)
  if (item) {
    detailsData.value = item
    detailsVisible.value = true
  }
  closeMenu()
}

onMounted(() => {
  loadData()
  window.addEventListener('click', closeMenu)
})

onUnmounted(() => {
  window.removeEventListener('click', closeMenu)
})
</script>

<template>
  <!-- 继续观看：网格结构与样式一致；禁用筛选，仅时间排序 -->
  <section class="continue-watch content mode-media">
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
    >
    </ListToolbar>

    <div v-if="showSort" class="panel panel--sort">
      <div class="row">
        <span>排序方向：</span>
        <label class="seg"><input type="radio" value="desc" v-model="sortOrder"> 最新在前</label>
        <label class="seg"><input type="radio" value="asc" v-model="sortOrder"> 最旧在前</label>
      </div>
      <p class="hint">仅按“最近进度更新时间”排序。</p>
    </div>

    <div v-if="showFilter" class="panel">
      <el-checkbox v-model="includeCompleted" @change="onToggleIncludeCompleted">包含已完播</el-checkbox>
    </div>

    <MediaGrid
      :items="gridItems"
      :dense="viewMode==='list'"
      :projector="projectAsset"
      :itemComponent="AssetCard"
      @open="openAsset"
      @play="openAsset"
      @contextmenu="onContextMenu"
    />

    <footer class="page-footer">
      <PaginationBar :page="page" :pageSize="pageSize" :total="total" @prev="prevPage" @next="nextPage" />
    </footer>

    <!-- Context Menu -->
    <div v-if="contextMenu.visible" 
         class="context-menu" 
         :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
         @click.stop>
      <div class="menu-item danger" @click="onDeleteHistory">删除播放记录</div>
      <div class="menu-item" @click="onShowDetails">播放记录详情</div>
    </div>

    <!-- Details Dialog -->
    <el-dialog v-model="detailsVisible" title="播放记录详情" width="600px">
      <div v-if="detailsData" class="details-content">
        <pre class="json-code">{{ JSON.stringify(detailsData, null, 2) }}</pre>
      </div>
    </el-dialog>
  </section>
  
</template>

<style scoped>
.content { padding-block: var(--space-5); max-width: none; width: 100%; padding-inline: var(--content-pad); }
.continue-watch { display: grid; gap: var(--space-4); }
.panel { border: 1px solid var(--border); background: color-mix(in oklab, var(--surface), var(--brand-weak) 4%); border-radius: var(--radius-lg); padding: var(--space-3); }
.panel--sort { margin-top: -4px; }
.row { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.seg { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); }
.hint { margin-top: var(--space-2); color: var(--text-muted); font-size: var(--text-sm); }
.page-footer { display: flex; justify-content: center; }
:global(html[data-theme="light"]) .page-footer { opacity: 0.9; }
:global(html[data-theme="dark"]) .page-footer { opacity: 1; }

.context-menu {
  position: fixed;
  z-index: 9999;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-2);
  padding: 4px 0;
  min-width: 160px;
}
.menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-primary);
  transition: background 0.2s;
}
.menu-item:hover {
  background: var(--surface-2);
}
.menu-item.danger {
  color: var(--error);
}
.details-content {
  max-height: 60vh;
  overflow-y: auto;
}
.json-code {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: monospace;
  font-size: 12px;
  background: var(--surface-2);
  padding: 12px;
  border-radius: var(--radius-sm);
  color: var(--text-primary);
}
</style>