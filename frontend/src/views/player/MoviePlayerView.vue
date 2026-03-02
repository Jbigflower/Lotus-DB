<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, onBeforeRouteLeave } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useMovieStore } from '@/stores/movie'
import { useAssetStore } from '@/stores/asset'
import { movieAssets } from '@/api'
import { buildAssetFileURL } from '@/api/movie_assets'
import { uploadUserAsset, listUserAssets, getUserAssetThumbnailsSigned, getUserAssetFile, getUserAsset } from '@/api/user_assets'
import { UserAssetType as UAType } from '@/types/user_asset'
import { ElMessage } from 'element-plus'
import PlayerShell from '@/components/player/PlayerShell.vue'
import PlayerControls from '@/components/player/PlayerControls.vue'
import SideActionBar from '@/components/player/SideActionBar.vue'
import { createWatchHistory, getWatchHistoryByAsset, updateWatchHistoryById } from '@/api/player'
import { WatchType, type WatchHistoryRead } from '@/types/watch_history'
import { formatTime } from '@/utils/formatTime'

const route = useRoute()
const userStore = useUserStore()
const movieStore = useMovieStore()
const assetStore = useAssetStore()

const src = ref<string>('')
const loading = ref(false)
const errorText = ref<string | null>(null)

const videoEl = ref<HTMLVideoElement | null>(null)
const playerRef = ref<InstanceType<typeof PlayerShell> | null>(null)
const current = ref(0)
const duration = ref(0)
const resumeAt = ref<number | null>(null)
const playing = ref(false)
const rate = ref(1)
const volume = ref(1)
const muted = ref(false)
const currentBitrate = ref<number | null>(null)
const bitrates = ref<number[]>([800, 1200, 2000, 4000])

const movieTitle = ref<string | null>(null)
const assetTitle = ref<string | null>(null)

const currentType = ref<'official' | 'user'>('official')
const currentAssetId = ref<string>('')

const officialAssetList = ref<Array<{ id: string; name: string; duration?: number }>>([])
const officialThumbMap = ref<Record<string, string>>({})
const userClipList = ref<Array<{ id: string; name: string; duration?: number }>>([])
const userThumbMap = ref<Record<string, string>>({})
const listContainerRef = ref<HTMLElement | null>(null)

const watchId = ref<string | null>(null)
let heartbeatTimer: number | null = null
let lastHeartbeatAt = 0
let accWatchSeconds = 0
let pageHideHandler: ((this: Window, ev: PageTransitionEvent) => any) | null = null

function getIds() {
  const id = String(route.params.id || '')
  const assetIdRaw = route.query.asset_id
  const assetId = typeof assetIdRaw === 'string' ? assetIdRaw : Array.isArray(assetIdRaw) ? assetIdRaw[0] : ''
  const startRaw = route.query.start
  const start = startRaw != null ? Number(Array.isArray(startRaw) ? startRaw[0] : startRaw) || 0 : undefined
  const sourceRaw = route.query.source
  const assetSource = typeof sourceRaw === 'string' ? sourceRaw : Array.isArray(sourceRaw) ? sourceRaw[0] : undefined
  return { movieId: id, assetId, start, assetSource }
}

async function load() {
  const token = userStore.token ?? ''
  const { movieId, assetId, start, assetSource } = getIds()
  if (!token || !assetId) { errorText.value = '未登录或缺少 asset_id'; return }
  loading.value = true; errorText.value = null
  try {
    // 先尝试获取或创建播放记录
    let record: WatchHistoryRead | null = null
    const type = assetSource === 'user' ? WatchType.Community : WatchType.Official
    currentType.value = assetSource === 'user' ? 'user' : 'official'
    currentAssetId.value = assetId
    try { record = await getWatchHistoryByAsset(token, assetId, type) } catch {}
    if (!record) {
      const device_info = { ua: navigator.userAgent }
      const payload = { movie_id: movieId, asset_id: assetId, type, last_position: start ?? 0, device_info }
      record = await createWatchHistory(token, payload as any)
    }
    watchId.value = record?.id ?? null

    const startPos = (record?.last_position ?? start ?? 0) || 0
    resumeAt.value = startPos
    if (currentType.value === 'official') {
      const signed = await movieAssets.getMovieAssetFile(token, assetId, { start: startPos })
      src.value = signed
    } else {
      const signed = await getUserAssetFile(token, assetId, { start: startPos })
      src.value = signed
    }
    if (movieId) { try { const m = await movieStore.fetchById(token, movieId); movieTitle.value = m.title } catch {} }
    if (assetId) {
      if (currentType.value === 'official') {
        try { const a = await movieAssets.getMovieAsset(token, assetId); assetTitle.value = a.name; assetStore.upsertEntity(a) } catch {}
      } else {
        try { const ua = await getUserAsset(token, assetId); assetTitle.value = ua.name } catch {}
      }
    }
  } catch {
    errorText.value = '无法获取签名URL'
  } finally {
    loading.value = false
  }
}

async function fetchLists() {
  try {
    const token = userStore.token ?? ''
    const { movieId } = getIds()
    if (!token || !movieId) return
    const page = await movieAssets.getMovieAssets(token, movieId)
    const vids = (page?.items ?? []).filter(a => a.type === 'video' && !a.is_deleted)
    officialAssetList.value = vids.map(a => ({ id: a.id, name: a.name, duration: (a.metadata as any)?.duration }))
    const offIds = vids.map(a => a.id)
    const offThumbs = offIds.length ? await movieAssets.getAssetThumbnailsSigned(token, offIds) : []
    officialThumbMap.value = Object.fromEntries(offIds.map((id, i) => [id, offThumbs[i] ?? '']))

    const res = await listUserAssets(token, { movie_ids: [movieId], asset_type: [UAType.CLIP], size: 100 })
    const uItems = (res as any)?.items ?? []
    userClipList.value = uItems.map((a: any) => ({ id: a.id, name: a.name, duration: (a.metadata as any)?.duration }))
    const uIds = uItems.map((a: any) => a.id)
    const uThumbs = uIds.length ? await getUserAssetThumbnailsSigned(token, uIds) : []
    userThumbMap.value = Object.fromEntries(uIds.map((id, i) => [id, uThumbs[i] ?? '']))
  } catch {}
}

function scrollActiveIntoView() {
  const container = listContainerRef.value
  if (!container) return
  const id = currentAssetId.value
  const el = container.querySelector(`[data-asset-id="${id}"]`) as HTMLElement | null
  if (el) el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
}

async function switchAsset(id: string, type: 'official' | 'user') {
  try {
    const token = userStore.token ?? ''
    const { movieId } = getIds()
    if (!token || !movieId) return
    currentType.value = type
    currentAssetId.value = id
    loading.value = true; errorText.value = null
    let record: WatchHistoryRead | null = null
    const wtype = type === 'user' ? WatchType.Community : WatchType.Official
    try { record = await getWatchHistoryByAsset(token, id, wtype) } catch {}
    if (!record) {
      const device_info = { ua: navigator.userAgent }
      const payload = { movie_id: movieId, asset_id: id, type: wtype, last_position: 0, device_info }
      record = await createWatchHistory(token, payload as any)
    }
    watchId.value = record?.id ?? null
    resumeAt.value = 0
    if (type === 'official') {
      src.value = await movieAssets.getMovieAssetFile(token, id, { start: 0 })
      try { const a = await movieAssets.getMovieAsset(token, id); assetTitle.value = a.name; assetStore.upsertEntity(a) } catch {}
    } else {
      src.value = await getUserAssetFile(token, id, { start: 0 })
      try { const ua = await getUserAsset(token, id); assetTitle.value = ua.name } catch {}
    }
    await nextTick()
    scrollActiveIntoView()
  } catch (e: any) {
    errorText.value = String(e?.message ?? '切换失败')
  } finally {
    loading.value = false
  }
}

function onReady(el: HTMLVideoElement) {
  videoEl.value = el
  el.addEventListener('loadedmetadata', () => {
    const t = Math.floor(resumeAt.value ?? 0)
    if (t > 0) {
      const d = Math.floor(el.duration || 0)
      const max = d > 0 ? Math.max(0, d - 2) : t
      el.currentTime = Math.min(t, max)
    }
  })
  // 完成事件
  el.addEventListener('ended', () => {
    const token = userStore.token ?? ''
    if (!token || !watchId.value) return
    const payload = { last_position: Math.floor(el.duration || current.value || 0), total_duration: Math.floor(el.duration || 0), last_watched: new Date().toISOString() }
    updateWatchHistoryById(token, watchId.value, payload as any).catch(() => {})
  })
  // 启动心跳
  lastHeartbeatAt = Date.now()
  heartbeatTimer = window.setInterval(() => {
    const token = userStore.token ?? ''
    if (!token || !watchId.value) return
    if (document.visibilityState !== 'visible') return
    const now = Date.now()
    const delta = Math.floor((now - lastHeartbeatAt) / 1000)
    lastHeartbeatAt = now
    if (!playing.value || delta <= 0) return
    accWatchSeconds += delta
    const payload = { last_position: Math.floor(current.value || 0), total_duration: Math.floor(duration.value || 0), total_watch_time: accWatchSeconds, last_watched: new Date().toISOString(), playback_rate: rate.value, device_info: { ua: navigator.userAgent } }
    updateWatchHistoryById(token, watchId.value, payload as any).catch(() => {})
  }, 30000)
  // 页面关闭兜底：sendBeacon
  pageHideHandler = () => {
    try {
      const token = userStore.token ?? ''
      if (!token || !watchId.value) return
      const body = JSON.stringify({ id: watchId.value, last_position: Math.floor(current.value || 0), total_duration: Math.floor(duration.value || 0), total_watch_time: accWatchSeconds, last_watched: new Date().toISOString() })
      const url = `${import.meta.env?.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api/v1/player/watch-histories/beacon?token=${encodeURIComponent(token)}`
      const ok = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))
      if (!ok) {
        const url2 = `${import.meta.env?.VITE_API_BASE_URL ?? 'http://localhost:8000'}/api/v1/player/watch-histories/${encodeURIComponent(watchId.value)}`
        const body2 = JSON.stringify({ last_position: Math.floor(current.value || 0), total_duration: Math.floor(duration.value || 0), total_watch_time: accWatchSeconds, last_watched: new Date().toISOString() })
        fetch(url2, {
          method: 'PATCH',
          keepalive: true,
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: body2,
        }).catch(() => {})
      }
    } catch {}
  }
  window.addEventListener('pagehide', pageHideHandler)
  // 首次就绪后，若已拿到时长，补写 total_duration
  try {
    const token = userStore.token ?? ''
    if (token && watchId.value) {
      const td = Math.floor(el.duration || 0)
      if (td > 0) {
        const payload = { total_duration: td }
        updateWatchHistoryById(token, watchId.value, payload as any).catch(() => {})
      }
    }
  } catch {}
}
function onTime(c: number, d: number) { current.value = c; duration.value = d }
function onState(p: boolean) {
  playing.value = p
  const token = userStore.token ?? ''
  const id = watchId.value
  if (!token || !id) return
  const payload = { last_position: Math.floor(current.value || 0), total_duration: Math.floor(duration.value || 0), last_watched: new Date().toISOString() }
  updateWatchHistoryById(token, id, payload as any).catch(() => {})
}

function togglePlay() {
  const v = videoEl.value; if (!v) return
  if (v.paused) v.play(); else v.pause()
}
function seekStep(delta: number) {
  const v = videoEl.value; if (!v) return
  v.currentTime = Math.max(0, Math.min(v.duration || 0, (v.currentTime || 0) + delta))
}
function onSeek(t: number) {
  const v = videoEl.value; if (!v) return
  v.currentTime = t
  const token = userStore.token ?? ''
  const id = watchId.value
  if (!token || !id) return
  const payload = { last_position: Math.floor(t), total_duration: Math.floor(duration.value || 0), last_watched: new Date().toISOString() }
  updateWatchHistoryById(token, id, payload as any).catch(() => {})
}
function onRate(r: number) {
  rate.value = r
  const v = videoEl.value; if (v) v.playbackRate = r
}
function onVolume(vv: number) {
  volume.value = vv
  const v = videoEl.value; if (v) { v.volume = vv; if (vv > 0) v.muted = false; muted.value = v.muted }
}
function onMute(m: boolean) { const v = videoEl.value; if (v) { v.muted = m; muted.value = m } }

async function onBitrate(br: number | null) {
  currentBitrate.value = br
  const token = userStore.token ?? ''
  const { assetId } = getIds()
  if (!token || !assetId) return
  const start = Math.floor(current.value || 0)
  
  if (br) {
    // 1. 转码模式：使用 buildAssetFileURL 构造后端直连 URL
    // 注意：转码模式下，我们希望播放器直接加载流，而不是等待 API 返回
    src.value = buildAssetFileURL(assetId, {
      transcode: true,
      target_bitrate_kbps: br,
      start: start
    }, token)
  } else {
    // 2. 原生/自动模式：调用 API 获取 Nginx 签名 URL
    try {
      const signed = await movieAssets.getMovieAssetFile(token, assetId, { start })
      src.value = signed
    } catch (e: any) {
      errorText.value = String(e?.message ?? '获取播放地址失败')
    }
  }
}

function toggleFullscreen() {
  const el = playerRef.value as any
  const root: HTMLElement | null = el?.container ?? null
  if (!root) return
  if (document.fullscreenElement) document.exitFullscreen()
  else root.requestFullscreen().catch(() => {})
}

function downloadBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

function onScreenshot() {
  const token = userStore.token ?? ''
  const { movieId } = getIds()
  if (!token || !movieId) { ElMessage.error('未登录或影片不存在'); return }
  const snapper = playerRef.value
  if (!snapper || typeof (snapper as any).snapshot !== 'function') { ElMessage.error('截图功能不可用'); return }
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  const name = `用户截图_${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
  ;(snapper as any).snapshot({ type: 'image/jpeg', quality: 0.92 })
    .then((blob: Blob) => uploadUserAsset(token, { movie_id: movieId, type: UAType.SCREENSHOT, name, file: blob, is_public: true }))
    .then(() => { ElMessage.success('已保存用户截图') })
    .catch((e: any) => { ElMessage.error(String(e?.message ?? '保存失败')) })
}

async function onCapture() { ElMessage.warning('当前还不支持动图保存') }

function onBookmark() { ElMessage.warning('当前还不支持') }

onMounted(async () => { await load(); await fetchLists(); await nextTick(); scrollActiveIntoView() })
onBeforeUnmount(() => {
  if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  if (pageHideHandler) { window.removeEventListener('pagehide', pageHideHandler); pageHideHandler = null }
})

onBeforeRouteLeave(() => {
  if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null }
  if (pageHideHandler) { window.removeEventListener('pagehide', pageHideHandler); pageHideHandler = null }
})
</script>

<template>
  <section class="content player-page">
    <div v-if="loading" class="hint">正在加载…</div>
    <div v-else-if="errorText" class="hint">{{ errorText }}</div>
    <div v-else>
      <PlayerShell ref="playerRef" :src="src" :movie-title="movieTitle" :asset-title="assetTitle" aspect="16:9" @ready="onReady" @timeupdate="onTime" @state="onState">
        <template #controls>
          <PlayerControls 
            class="overlay-layer" 
            :playing="playing" 
            :rate="rate" 
            :volume="volume" 
            :muted="muted" 
            :bitrates="bitrates" 
            :current-bitrate="currentBitrate" 
            :current="current"
            :duration="duration"
            @toggle="togglePlay" 
            @seek="onSeek"
            @seekStep="seekStep" 
            @rate="onRate" 
            @volume="onVolume" 
            @mute="onMute" 
            @bitrate="onBitrate" 
            @fullscreen="toggleFullscreen" 
            @settings="() => {}" 
          />
        </template>
        <template #side>
          <SideActionBar :side="'right'" :visible="true" @screenshot="onScreenshot" @capture="onCapture" @bookmark="onBookmark" />
        </template>
      </PlayerShell>
      <div ref="listContainerRef" class="asset-strip">
        <div v-if="currentType === 'official'" class="strip-items">
          <button
            v-for="(a, idx) in officialAssetList"
            :key="a.id"
            class="asset-card"
            :class="{ 'is-active': a.id === currentAssetId }"
            :data-asset-id="a.id"
            @click="switchAsset(a.id, 'official')"
          >
            <img v-if="officialThumbMap[a.id]" :src="officialThumbMap[a.id]" class="thumb" alt="" />
            <div class="meta">
              <div class="title">{{ a.name || `第${idx+1}集` }}</div>
              <div class="sub">{{ idx + 1 }} · {{ formatTime(a.duration ?? 0) }}</div>
            </div>
          </button>
        </div>
        <div v-else class="strip-items">
          <button
            v-for="(a, idx) in userClipList"
            :key="a.id"
            class="asset-card"
            :class="{ 'is-active': a.id === currentAssetId }"
            :data-asset-id="a.id"
            @click="switchAsset(a.id, 'user')"
          >
            <img v-if="userThumbMap[a.id]" :src="userThumbMap[a.id]" class="thumb" alt="" />
            <div class="meta">
              <div class="title">{{ a.name || `剪辑 ${idx+1}` }}</div>
              <div class="sub">{{ idx + 1 }} · {{ formatTime(a.duration ?? 0) }}</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  </section>
  
</template>

<style scoped>
.player-page { padding: var(--space-5); display: grid; gap: var(--space-4); }
.hint { color: var(--text-muted); }
.asset-strip { display: block; overflow-x: auto; padding-bottom: var(--space-2); }
.strip-items { display: inline-flex; gap: var(--space-3); }
.asset-card { display: inline-flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-3); border-radius: 8px; background: var(--bg-elevated); color: var(--text-primary); border: 1px solid var(--border-color); }
.asset-card.is-active { outline: 2px solid var(--brand); border-color: var(--brand); background: var(--bg-active); }
.thumb { width: 120px; height: 68px; object-fit: cover; border-radius: 6px; background: var(--bg-muted); }
.meta { display: grid; gap: 4px; text-align: left; }
.title { font-weight: 600; }
.sub { font-size: 12px; color: var(--text-muted); }
</style>