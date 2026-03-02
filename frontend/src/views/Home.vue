<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import LibraryCard from '@/components/ui/LibraryCard.vue'
import MediaCard from '@/components/ui/MediaCard.vue'
import AssetCard from '@/components/ui/AssetCard.vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useLibraryStore } from '@/stores/library'
import { useMovieStore } from '@/stores/movie'
import { useWatchHistoryStore } from '@/stores/watch_history'
import { useUserCollectionsStore } from '@/stores/user_collections'
import { CustomListType } from '@/types/user_collection'
import { users, libraries, movies, movieAssets } from '@/api'
import { useAssetStore } from '@/stores/asset'
// 组件命名为多词，避免 lint 警告
defineOptions({ name: 'HomePage' })

const router = useRouter()

// 数据源（接入真实数据）
const homeLibraries = ref<any[]>([])
const coverUrls = ref<Record<string, string>>({})
const ownerNames = ref<Record<string, string>>({})
const ownerAvatars = ref<Record<string, string>>({})
const continueWatching = ref<any[]>([])
const assetThumbs = ref<Record<string, string>>({})
const assetTitles = ref<Record<string, string>>({})
const isContinueLoading = ref(true)
const recentAdded = ref<any[]>([])

const userStore = useUserStore()
const libraryStore = useLibraryStore()
const movieStore = useMovieStore()
const assetStore = useAssetStore()
const watchStore = useWatchHistoryStore()
const collStore = useUserCollectionsStore()

async function loadLibraries() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try {
    await libraryStore.fetchList(token, { page: 1, page_size: 8 })
    homeLibraries.value = libraryStore.list.slice(0, 8)
    const libIds = homeLibraries.value.map((l:any) => l.id)
    if (libIds.length) {
      try {
        const urls = await libraries.getLibraryCoversSigned(token, libIds)
        const map: Record<string, string> = {}
        for (let i = 0; i < libIds.length; i++) map[libIds[i]] = urls[i]
        coverUrls.value = { ...coverUrls.value, ...map }
      } catch {}
    }
    const ids = Array.from(new Set(homeLibraries.value.map((l:any) => l.user_id).filter(Boolean))) as string[]
    if (ids.length) {
      try {
        const mapping = await users.getUserMapping(token, ids)
        ownerNames.value = { ...ownerNames.value, ...mapping }
      } catch {}
      try {
        const urls = await users.getUserProfilesSigned(token, ids)
        const map: Record<string, string> = {}
        for (let i = 0; i < ids.length; i++) map[ids[i]] = urls[i]
        ownerAvatars.value = { ...ownerAvatars.value, ...map }
      } catch {}
      const selfId = userStore.user?.id
      const selfName = userStore.user?.username
      if (selfId && selfName && !ownerNames.value[selfId]) ownerNames.value[selfId] = selfName
    }
  } catch { /* noop */ }
}

async function loadContinueWatching() {
  const token = userStore.token ?? ''
  isContinueLoading.value = true
  if (!token) { ElMessage.error('未登录'); isContinueLoading.value = false; return }
  try {
    const recent = await watchStore.fetchRecent(token, 8)
    const assetIds = recent.map(r => r.asset_id).filter(Boolean) as string[]
    if (assetIds.length) {
      try {
        const urls = await movieAssets.getAssetThumbnailsSigned(token, assetIds)
        const map: Record<string, string> = {}
        for (let i = 0; i < assetIds.length; i++) { const u = urls[i]; if (u) map[assetIds[i]] = u }
        assetThumbs.value = { ...assetThumbs.value, ...map }
      } catch {}
      for (const aid of assetIds) {
        if (!assetTitles.value[aid]) {
          try { const a = await movieAssets.getMovieAsset(token, aid); assetStore.upsertEntity(a); assetTitles.value[aid] = a.name }
          catch {}
        }
      }
    }
    const movieIds = Array.from(new Set(recent.map(r => r.movie_id).filter(Boolean))) as string[]
    for (const mid of movieIds) {
      const cached = movieStore.$state.entities?.[mid]
      if (!cached) { try { await movieStore.fetchById(token, mid) } catch {} }
    }

    continueWatching.value = recent.map(r => {
      const m = r.movie_id ? movieStore.$state.entities?.[r.movie_id] : null
      const movieTitle = m?.title_cn ?? m?.title ?? ''
      const lastWatched = r.last_watched ?? undefined
      const denom = r.total_duration ?? 0
      const progressPercent = denom > 0 ? Math.max(0, Math.min(100, (r.last_position / denom) * 100)) : 0
      return {
        movieId: r.movie_id,
        assetId: r.asset_id,
        assetTitle: assetTitles.value[r.asset_id] ?? undefined,
        movieTitle,
        thumbnailUrl: assetThumbs.value[r.asset_id] ?? undefined,
        lastWatchedAt: lastWatched,
        progressPercent,
      }
    })
  } catch { /* noop */ } finally { isContinueLoading.value = false }
}

async function loadRecentAdded() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try {
    await movieStore.fetchRecent(token, { size: 8 })
    const slice = movieStore.list.slice(0, 8)
    const ids = slice.map(m => m.id)
    let urls: string[] = []
    try { urls = await movies.getMovieCoversSigned(token, ids, 'poster.jpg') } catch {}
    const coverMap: Record<string, string> = {}
    for (let i = 0; i < ids.length; i++) { const u = urls[i]; if (u) coverMap[ids[i]] = u }
    recentAdded.value = slice.map(m => ({
      ...m,
      poster: coverMap[m.id] ?? undefined,
    }))
  } catch { /* noop */ }
}

onMounted(() => {
  loadLibraries()
  loadContinueWatching()
  loadRecentAdded()
})

function seeMoreLibraries() { router.push('/libraries') }
function seeMoreContinue() { router.push('/continue') }
function seeMoreRecent() { router.push('/recent') }
function openLibrary(id: string) { router.push(`/libraries/${id}`) }
function openMovie(id: string) { router.push(`/movies/${id}`) }
function openPlayer(id: string) { router.push(`/player/${id}`) }
function openPlayerWithAsset(movieId?: string, assetId?: string) {
  if (!movieId || !assetId) return
  router.push({ path: `/player/${movieId}` , query: { asset_id: assetId } })
}

</script>

<template>
  <div class="home-page mode-media">
    <!-- 我的媒体库 -->
    <section class="home-section">
      <div class="home-section__header">
        <h2 class="home-section__title">我的媒体库</h2>
        <button class="btn btn--ghost" @click="seeMoreLibraries">查看更多</button>
      </div>
      <div class="card-row libraries-row" v-if="homeLibraries.length">
        <div v-for="lib in homeLibraries" :key="lib.id" class="card-item">
          <LibraryCard
            :library="lib"
            :cover-url="coverUrls[lib.id]"
            :user-name="ownerNames[lib.user_id]"
            :user-avatar-url="ownerAvatars[lib.user_id]"
            @open="openLibrary"
          />
        </div>
      </div>
      <div class="loading" v-else>正在加载媒体库…</div>
    </section>

    <!-- 继续观看 -->
    <section class="home-section">
      <div class="home-section__header">
        <h2 class="home-section__title">继续观看</h2>
        <button class="btn btn--ghost" @click="seeMoreContinue">查看更多</button>
      </div>
      <div class="loading" v-if="isContinueLoading">正在加载观看历史…</div>
      <div class="card-row media-row" v-else-if="continueWatching.length">
        <div v-for="item in continueWatching" :key="item.assetId" class="card-item">
          <AssetCard
            :id="item.assetId"
            :asset-title="item.assetTitle"
            :movie-title="item.movieTitle"
            :movie-id="item.movieId"
            :thumbnail-url="item.thumbnailUrl"
            :last-watched-at="item.lastWatchedAt"
            :progress-percent="item.progressPercent"
            :show-progress="true"
            @play="() => openPlayerWithAsset(item.movieId, item.assetId)"
            @click-movie="(mid) => openMovie(String(mid))"
          />
        </div>
      </div>
      <div class="loading" v-else>最近无观看历史</div>
    </section>

    <!-- 最近添加 -->
    <section class="home-section">
      <div class="home-section__header">
        <h2 class="home-section__title">最近添加</h2>
        <button class="btn btn--ghost" @click="seeMoreRecent">查看更多</button>
      </div>
      <div class="card-row media-row" v-if="recentAdded.length">
        <div v-for="m in recentAdded" :key="m.id" class="card-item">
          <MediaCard
            :id="m.id"
            :title="m.title"
            :poster="m.poster"
            :year="m.release_date ? Number(String(m.release_date).slice(0,4)) : undefined"
            :rating="m.rating ?? undefined"
            :genres="m.genres"
            :tags="m.tags"
            :is-favorite="m.is_favoriter === true"
            :in-watch-later="m.is_watchLater === true"
            @open="openMovie"
            @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
            @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
          />
        </div>
      </div>
      <div class="loading" v-else>正在加载最新内容…</div>
    </section>
  </div>
  
</template>

<style scoped>
.home-page {
  padding: clamp(16px, 4vw, 32px);
  display: grid;
  gap: clamp(24px, 4vw, 40px);
  background: linear-gradient(180deg,
    color-mix(in oklab, var(--surface-2), black 8%),
    color-mix(in oklab, var(--surface), var(--brand-weak) 6%)
  );
}

.home-section {
  display: grid;
  gap: 12px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  border-radius: var(--radius);
  box-shadow: var(--shadow-1);
  padding: clamp(12px, 2.4vw, 18px);
}
.home-section__header { display: flex; align-items: baseline; justify-content: space-between; }
.home-section__title {
  margin: 0;
  font-size: clamp(var(--text-xl), 3.4vw, 2rem);
  color: var(--text-primary);
  letter-spacing: 0.3px;
}

.btn { cursor: pointer; }
.btn--ghost {
  color: var(--text-secondary);
  border: 1px solid var(--border);
  background: transparent;
  border-radius: var(--radius-pill);
  padding: 6px 12px;
  font-size: var(--text-sm);
}
.btn--ghost:hover { background: color-mix(in oklab, var(--surface-2), var(--brand-weak) 16%); }

.card-row {
  display: grid;
  grid-auto-flow: column;
  gap: 12px;
  overflow-x: auto;
  padding-inline: 14px;
  overflow-y: visible;
  padding-block: 14px;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
}
.card-item { scroll-snap-align: start; overflow: visible; }

/* 宽度与比例：区分两类卡片的横滑列宽 */
.libraries-row { grid-auto-columns: clamp(280px, 24vw, 360px); }
.media-row { grid-auto-columns: clamp(240px, 22vw, 320px); }

.loading {
  color: var(--text-muted);
  padding: 10px 0;
}

@media (min-width: 1440px) {
  .home-page { gap: 48px; }
}
</style>
