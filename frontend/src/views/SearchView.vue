<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useSearchStore } from '@/stores/search'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import LibraryCard from '@/components/ui/LibraryCard.vue'
import AssetCard from '@/components/ui/AssetCard.vue'
import { useMovieStore } from '@/stores/movie'
import { movieAssets, userAssets } from '@/api'
import { AssetType } from '@/types/asset'
import { UserAssetType } from '@/types/user_asset'
import type { MovieRead } from '@/types/movie'
import type { AssetRead } from '@/types/asset'
import type { UserAssetRead } from '@/types/user_asset'

const userStore = useUserStore()
const searchStore = useSearchStore()
const movieStore = useMovieStore()
const router = useRouter()
const route = useRoute()

const q = ref(searchStore.query || '')
const activeTab = ref(searchStore.activeType || 'summary')
const movieCoverMap = ref<Record<string, string>>({})
const movieAssetThumbMap = ref<Record<string, string>>({})
const userAssetThumbMap = ref<Record<string, string>>({})

// Initialize from URL query params
onMounted(() => {
  const urlQ = route.query.q as string
  const urlType = route.query.type as string
  
  if (urlQ) {
    q.value = urlQ
    searchStore.setQuery(urlQ)
  }
  
  if (urlType && ['summary', 'movies', 'libraries', 'user_assets', 'collections', 'movie_assets'].includes(urlType)) {
    activeTab.value = urlType
    searchStore.setActiveType(urlType)
  }

  // Trigger search if we have query
  if (q.value.trim()) {
    doSearch(activeTab.value)
  }
})

// Sync local activeTab with store
watch(activeTab, (val) => {
  searchStore.setActiveType(val)
  // Update URL
  router.replace({ query: { ...route.query, type: val } })
  
  // Only trigger search if we already have a query, otherwise it's just a tab switch ready for next search
  if (q.value.trim()) {
      if (val !== 'summary' && searchStore.results) {
         doSearch(val)
      } else if (val === 'summary') {
         doSearch('summary')
      }
  }
})

// Sync local q with store query
watch(() => searchStore.query, (val) => {
  if (val !== q.value) q.value = val
})

type MovieSearchItem = MovieRead & { poster?: string | null }
type MovieAssetItem = AssetRead & { movie_title?: string | null; movie?: { title?: string | null } | null }
type UserAssetItem = UserAssetRead & { movie_info?: { title?: string | null } | null }

function shouldRequestMovieAssetThumbnail(raw: MovieAssetItem) {
  const type = raw.type
  if (type === AssetType.SUBTITLE) return false
  if (type === AssetType.IMAGE) return true
  if (type === AssetType.VIDEO) {
    const meta = raw.metadata as { has_thumbnail?: boolean } | undefined
    return meta?.has_thumbnail === true
  }
  return false
}

function shouldRequestUserAssetThumbnail(raw: UserAssetItem) {
  const type = raw.type
  if (type === UserAssetType.NOTE || type === UserAssetType.REVIEW) return false
  if (type === UserAssetType.SCREENSHOT) return true
  if (type === UserAssetType.CLIP) {
    const meta = raw.metadata as { has_thumbnail?: boolean } | undefined | null
    return meta?.has_thumbnail === true
  }
  return false
}

function resolveMoviePoster(raw: MovieSearchItem) {
  const id = String(raw.id ?? '')
  const fromMap = id ? movieCoverMap.value[id] : undefined
  const fallback = typeof raw.poster === 'string' && raw.poster ? raw.poster : undefined
  return fromMap ?? fallback
}

function resolveMovieAssetThumbnail(raw: MovieAssetItem) {
  if (!shouldRequestMovieAssetThumbnail(raw)) return undefined
  const id = String(raw.id ?? '')
  const fromMap = id ? movieAssetThumbMap.value[id] : undefined
  const fallback = typeof (raw as { thumbnail?: unknown }).thumbnail === 'string' && (raw as { thumbnail?: string }).thumbnail
    ? (raw as { thumbnail?: string }).thumbnail
    : undefined
  return fromMap ?? fallback
}

function resolveUserAssetThumbnail(raw: UserAssetItem) {
  if (!shouldRequestUserAssetThumbnail(raw)) return undefined
  const id = String(raw.id ?? '')
  const fromMap = id ? userAssetThumbMap.value[id] : undefined
  const fallback = typeof (raw as { thumbnail?: unknown }).thumbnail === 'string' && (raw as { thumbnail?: string }).thumbnail
    ? (raw as { thumbnail?: string }).thumbnail
    : undefined
  return fromMap ?? fallback
}

async function loadCardBackgrounds() {
  const token = userStore.token ?? ''
  if (!token) return
  const res = searchStore.results
  if (!res) return

  const movieItems = res.movies.items as MovieSearchItem[]
  const movieIds = Array.from(new Set(movieItems.map((m) => String(m.id)).filter(Boolean)))
  const missingMovieIds = movieIds.filter((id) => !movieCoverMap.value[id])
  if (missingMovieIds.length) {
    try {
      const urls = await movieStore.getCoversSigned(token, missingMovieIds, 'poster.jpg')
      const map: Record<string, string> = {}
      missingMovieIds.forEach((id, idx) => {
        const url = urls[idx]
        if (url) map[id] = url
      })
      movieCoverMap.value = { ...movieCoverMap.value, ...map }
    } catch {}
  }

  const movieAssetItems = res.movie_assets.items as MovieAssetItem[]
  const movieAssetIds = movieAssetItems
    .filter(shouldRequestMovieAssetThumbnail)
    .map((a) => String(a.id))
    .filter(Boolean)
  const missingMovieAssetIds = movieAssetIds.filter((id) => !movieAssetThumbMap.value[id])
  if (missingMovieAssetIds.length) {
    try {
      const urls = await movieAssets.getAssetThumbnailsSigned(token, missingMovieAssetIds)
      const map: Record<string, string> = {}
      missingMovieAssetIds.forEach((id, idx) => {
        const url = urls[idx]
        if (url) map[id] = url
      })
      movieAssetThumbMap.value = { ...movieAssetThumbMap.value, ...map }
    } catch {}
  }

  const userAssetItems = res.user_assets.items as UserAssetItem[]
  const userAssetIds = userAssetItems
    .filter(shouldRequestUserAssetThumbnail)
    .map((a) => String(a.id))
    .filter(Boolean)
  const missingUserAssetIds = userAssetIds.filter((id) => !userAssetThumbMap.value[id])
  if (missingUserAssetIds.length) {
    try {
      const urls = await userAssets.getUserAssetThumbnailsSigned(token, missingUserAssetIds)
      const map: Record<string, string> = {}
      missingUserAssetIds.forEach((id, idx) => {
        const url = urls[idx]
        if (url) map[id] = url
      })
      userAssetThumbMap.value = { ...userAssetThumbMap.value, ...map }
    } catch {}
  }
}

async function doSearch(type: string = 'summary') {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  
  if (!q.value.trim()) return

  searchStore.setQuery(q.value)
  searchStore.setActiveType(type)
  
  // Update URL
  router.replace({ query: { ...route.query, q: q.value, type } })
  
  // If we are switching tabs or starting new search, reset page to 1
  // However, if we are just searching, we might want to keep page?
  // Usually new search -> page 1.
  if (searchStore.page !== 1) {
      searchStore.setPage(1)
  }
  
  try {
    await searchStore.search(token, q.value, type)
    await loadCardBackgrounds()
  } catch {
    ElMessage.error('搜索失败')
  }
}

function handlePageChange(newPage: number) {
  searchStore.setPage(newPage)
  doSearch(activeTab.value)
}

// Projectors (Copied from original)
function projectLibrary(raw: unknown) {
  const item = raw as { id?: string | number }
  return { id: item?.id, library: raw }
}
function projectMovie(raw: unknown) {
  const item = raw as MovieSearchItem
  const id = String(item?.id ?? '')
  const ent = movieStore.entities[id]
  return {
    id,
    title: item?.title,
    poster: item ? resolveMoviePoster(item) : undefined,
    rating: item?.rating ?? undefined,
    tags: item?.tags,
    isFavorite: ent?.is_favoriter === true,
    inWatchLater: ent?.is_watchLater === true,
  }
}
function projectMovieAsset(raw: unknown) {
  const item = raw as MovieAssetItem
  return {
    id: item?.id,
    assetTitle: item?.name ?? '资产',
    movieTitle: (item?.movie_title ?? item?.movie?.title ?? ''),
    thumbnailUrl: item ? resolveMovieAssetThumbnail(item) : undefined,
    movieId: item?.movie_id,
  }
}
function projectUserAsset(raw: unknown) {
  const item = raw as UserAssetItem
  return {
    id: item?.id,
    assetTitle: item?.name ?? '用户资产',
    movieTitle: (item?.movie_info?.title ?? ''),
    thumbnailUrl: item ? resolveUserAssetThumbnail(item) : undefined,
    movieId: item?.movie_id,
  }
}
function getMovieAsset(assetId: string | number): MovieAssetItem | null {
  const items = (searchStore.results?.movie_assets?.items ?? []) as MovieAssetItem[]
  const idStr = String(assetId)
  return items.find((it) => String(it?.id) === idStr) ?? null
}
function getUserAsset(assetId: string | number): UserAssetItem | null {
  const items = (searchStore.results?.user_assets?.items ?? []) as UserAssetItem[]
  const idStr = String(assetId)
  return items.find((it) => String(it?.id) === idStr) ?? null
}

const hasResults = computed(() => !!searchStore.results)
const isSummary = computed(() => activeTab.value === 'summary')

// Helper to get total count for a tab
function getCount(type: string) {
    if (!searchStore.results) return 0
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const results = searchStore.results as any
    return results[type]?.total ?? 0
}

watch(() => searchStore.results, () => {
  loadCardBackgrounds()
})
</script>

<template>
  <section
    class="search-page"
    :style="!hasResults && !searchStore.loading ? { justifyContent: 'center', alignItems: 'center', paddingBottom: '20vh' } : undefined"
  >
    <div class="search-header">
       <h1 v-if="!hasResults && !searchStore.loading" class="brand-title">Lotus DB Search</h1>
       <div class="search-bar">
          <input 
            class="search-input" 
            v-model="q" 
            placeholder="搜索电影、媒体库、资产..." 
            @keyup.enter="doSearch('summary')"
          />
          <button class="btn-search" @click="doSearch('summary')">
             🔍
          </button>
       </div>
    </div>

    <!-- Tabs -->
    <div v-if="hasResults || searchStore.loading" class="tabs-container">
       <div class="tabs">
          <button 
            v-for="tab in ['summary', 'movies', 'libraries', 'user_assets', 'collections', 'movie_assets']"
            :key="tab"
            class="tab-item"
            :class="{ active: activeTab === tab }"
            @click="activeTab = tab"
          >
             {{ 
                tab === 'summary' ? '综合' : 
                tab === 'movies' ? '电影' :
                tab === 'libraries' ? '媒体库' :
                tab === 'user_assets' ? '用户资产' :
                tab === 'collections' ? '片单' : '电影资产'
             }}
             <span v-if="tab !== 'summary' && getCount(tab) > 0" class="badge">{{ getCount(tab) }}</span>
          </button>
       </div>
    </div>

    <!-- Content -->
    <div v-if="searchStore.loading" class="loading-state">
       <div class="spinner"></div>
       <p>搜索中...</p>
    </div>

    <div v-else-if="searchStore.results" class="results-container">
       
       <!-- Summary View -->
       <div v-if="isSummary" class="summary-view">
          
          <!-- Movies Section -->
          <section v-if="searchStore.results.movies.total > 0" class="section">
             <div class="section-header">
                <h3>电影</h3>
                <button class="btn-link" @click="activeTab = 'movies'">查看全部 ({{searchStore.results.movies.total}})</button>
             </div>
             <MediaGrid
               :items="searchStore.results.movies.items.slice(0, 5)"
               :projector="projectMovie"
               @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
               @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
               @open="(id) => router.push(`/movies/${id}`)"
               class="summary-grid"
             />
          </section>

          <!-- Libraries Section -->
          <section v-if="searchStore.results.libraries.total > 0" class="section">
             <div class="section-header">
                <h3>媒体库</h3>
                <button class="btn-link" @click="activeTab = 'libraries'">查看全部 ({{searchStore.results.libraries.total}})</button>
             </div>
             <MediaGrid
               :items="searchStore.results.libraries.items.slice(0, 5)"
               :item-component="LibraryCard"
               :projector="projectLibrary"
               @open="(id) => router.push(`/libraries/${id}`)"
               class="summary-grid"
             />
          </section>

          <!-- User Assets -->
           <section v-if="searchStore.results.user_assets.total > 0" class="section">
             <div class="section-header">
                <h3>用户资产</h3>
                <button class="btn-link" @click="activeTab = 'user_assets'">查看全部 ({{searchStore.results.user_assets.total}})</button>
             </div>
             <MediaGrid
                :items="searchStore.results.user_assets.items.slice(0, 5)"
                :item-component="AssetCard"
                :projector="projectUserAsset"
                @play="(id) => { const it = getUserAsset(id); if (it?.movie_id) router.push({ path: `/player/${it.movie_id}`, query: { asset_id: String(id), source: 'user' } }) }"
                @click-movie="(mid) => router.push(`/movies/${mid}`)"
                class="summary-grid"
              />
          </section>
          
          <!-- Collections -->
           <section v-if="searchStore.results.collections.total > 0" class="section">
             <div class="section-header">
                <h3>片单</h3>
                <button class="btn-link" @click="activeTab = 'collections'">查看全部 ({{searchStore.results.collections.total}})</button>
             </div>
             <ul class="list">
                <li v-for="c in searchStore.results.collections.items.slice(0, 5)" :key="c.id" @click="router.push(`/lists/${c.id}`)" class="list-item">
                  <strong>{{ c.name }}</strong>
                  <span class="tag">{{ c.type }}</span>
                </li>
             </ul>
          </section>

       </div>

       <!-- Detailed View -->
       <div v-else class="detailed-view">
          <template v-if="activeTab === 'movies'">
             <MediaGrid
               :items="searchStore.results.movies.items"
               :projector="projectMovie"
               @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
               @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
               @open="(id) => router.push(`/movies/${id}`)"
             />
             <div class="pagination" v-if="searchStore.results.movies.pages > 1">
                <button :disabled="searchStore.page <= 1" @click="handlePageChange(searchStore.page - 1)">上一页</button>
                <span>{{ searchStore.page }} / {{ searchStore.results.movies.pages }}</span>
                <button :disabled="searchStore.page >= searchStore.results.movies.pages" @click="handlePageChange(searchStore.page + 1)">下一页</button>
             </div>
          </template>

          <template v-else-if="activeTab === 'libraries'">
             <MediaGrid
               :items="searchStore.results.libraries.items"
               :item-component="LibraryCard"
               :projector="projectLibrary"
               @open="(id) => router.push(`/libraries/${id}`)"
             />
              <div class="pagination" v-if="searchStore.results.libraries.pages > 1">
                <button :disabled="searchStore.page <= 1" @click="handlePageChange(searchStore.page - 1)">上一页</button>
                <span>{{ searchStore.page }} / {{ searchStore.results.libraries.pages }}</span>
                <button :disabled="searchStore.page >= searchStore.results.libraries.pages" @click="handlePageChange(searchStore.page + 1)">下一页</button>
             </div>
          </template>

          <template v-else-if="activeTab === 'user_assets'">
             <MediaGrid
                :items="searchStore.results.user_assets.items"
                :item-component="AssetCard"
                :projector="projectUserAsset"
                @play="(id) => { const it = getUserAsset(id); if (it?.movie_id) router.push({ path: `/player/${it.movie_id}`, query: { asset_id: String(id), source: 'user' } }) }"
                @click-movie="(mid) => router.push(`/movies/${mid}`)"
              />
               <div class="pagination" v-if="searchStore.results.user_assets.pages > 1">
                  <button :disabled="searchStore.page <= 1" @click="handlePageChange(searchStore.page - 1)">上一页</button>
                  <span>{{ searchStore.page }} / {{ searchStore.results.user_assets.pages }}</span>
                  <button :disabled="searchStore.page >= searchStore.results.user_assets.pages" @click="handlePageChange(searchStore.page + 1)">下一页</button>
               </div>
          </template>
          
           <template v-else-if="activeTab === 'collections'">
              <ul class="list">
                <li v-for="c in searchStore.results.collections.items" :key="c.id" @click="router.push(`/lists/${c.id}`)" class="list-item">
                  <strong>{{ c.name }}</strong>
                  <span class="tag">{{ c.type }}</span>
                  <span v-if="c.is_public" class="tag tag--public">公开</span>
                </li>
             </ul>
              <div class="pagination" v-if="searchStore.results.collections.pages > 1">
                  <button :disabled="searchStore.page <= 1" @click="handlePageChange(searchStore.page - 1)">上一页</button>
                  <span>{{ searchStore.page }} / {{ searchStore.results.collections.pages }}</span>
                  <button :disabled="searchStore.page >= searchStore.results.collections.pages" @click="handlePageChange(searchStore.page + 1)">下一页</button>
               </div>
          </template>
          
          <template v-else-if="activeTab === 'movie_assets'">
             <MediaGrid
                :items="searchStore.results.movie_assets.items"
                :item-component="AssetCard"
                :projector="projectMovieAsset"
                @play="(id) => { const it = getMovieAsset(id); if (it?.movie_id) router.push({ path: `/player/${it.movie_id}`, query: { asset_id: String(id) } }) }"
                @click-movie="(mid) => router.push(`/movies/${mid}`)"
              />
               <div class="pagination" v-if="searchStore.results.movie_assets.pages > 1">
                  <button :disabled="searchStore.page <= 1" @click="handlePageChange(searchStore.page - 1)">上一页</button>
                  <span>{{ searchStore.page }} / {{ searchStore.results.movie_assets.pages }}</span>
                  <button :disabled="searchStore.page >= searchStore.results.movie_assets.pages" @click="handlePageChange(searchStore.page + 1)">下一页</button>
               </div>
          </template>

       </div>
    </div>
    
    <!-- Empty State -->
    <div v-if="!searchStore.loading && hasResults && getCount('movies') === 0 && getCount('libraries') === 0 && getCount('user_assets') === 0 && getCount('collections') === 0" class="empty-state">
       <p>未找到相关结果</p>
    </div>

  </section>
</template>

<style scoped>
.search-page {
  padding: 20px 40px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  width: 100%;
}

.brand-title {
  font-size: 2.5rem;
  margin-bottom: 2rem;
  color: var(--text-primary);
  text-align: center;
  font-weight: 300;
  letter-spacing: 1px;
}

.search-header {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
}

.search-bar {
  display: flex;
  background: var(--surface);
  border-radius: 50px;
  padding: 8px 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  border: 1px solid var(--border);
  transition: all 0.3s ease;
}

.search-bar:focus-within {
  box-shadow: 0 6px 16px rgba(0,0,0,0.15);
  border-color: var(--primary);
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  font-size: 1.1rem;
  padding: 8px;
  color: var(--text);
  outline: none;
}

.btn-search {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 1.2rem;
  padding: 0 8px;
}

.tabs-container {
  margin-top: 2rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
}

.tabs {
  display: flex;
  gap: 2rem;
  justify-content: center;
}

.tab-item {
  background: transparent;
  border: none;
  padding: 12px 0;
  font-size: 1rem;
  color: var(--text-secondary);
  cursor: pointer;
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tab-item.active {
  color: var(--primary);
  font-weight: 500;
}

.tab-item.active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--primary);
}

.badge {
  background: var(--surface-variant);
  color: var(--text-secondary);
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: 10px;
}

.tab-item.active .badge {
  background: var(--primary);
  color: white;
}

.section {
  margin-bottom: 3rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.section-header h3 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 500;
}

.btn-link {
  background: transparent;
  border: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 0.9rem;
}

.btn-link:hover {
  text-decoration: underline;
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin-top: 2rem;
}

.pagination button {
  padding: 8px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  color: var(--text);
}

.pagination button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.list {
  list-style: none;
  padding: 0;
}

.list-item {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
}

.list-item:hover {
  background: var(--surface-hover);
}

.tag {
  background: var(--surface-variant);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.8rem;
}

.tag--public {
  background: var(--success-bg);
  color: var(--success);
}

.loading-state, .empty-state {
  text-align: center;
  padding: 4rem;
  color: var(--text-secondary);
}

.spinner {
  /* Simple spinner */
  width: 40px;
  height: 40px;
  border: 4px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
