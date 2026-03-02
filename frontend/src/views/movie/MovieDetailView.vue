<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ContextMenu, { type MenuItem } from '@/components/ui/ContextMenu.vue'
import { useMovieStore } from '@/stores/movie'
import { useUserStore } from '@/stores/user'
import { useAssetStore } from '@/stores/asset'
import { useUserAssetsStore } from '@/stores/user_assets'
import { useUserCollectionsStore } from '@/stores/user_collections'
import { CustomListType } from '@/types/user_collection'
import { AssetType } from '@/types/asset'
import { UserAssetType } from '@/types/user_asset'
import type { UserAssetRead } from '@/types/user_asset'
import { movieAssets, movies as moviesApi, userAssets, users as usersApi } from '@/api'
import { useWatchHistoryStore } from '@/stores/watch_history'
import { WatchType } from '@/types/watch_history'
import { UserRole } from '@/types/user'
import { ElMessage } from 'element-plus'

interface AssetMeta {
  duration?: number
  quality?: string
  size?: number
  width?: number
  height?: number
  language?: string
  [key: string]: unknown
}

// 路由参数：电影 ID（后续可接入真实接口）
const route = useRoute()
const router = useRouter()
const movieId = computed(() => String(route.params.id ?? ''))

// 语言切换：原文 / 用户译文
type LangView = 'origin' | 'user'
const langView = ref<LangView>('user')

// Hero 区基础信息（接入后端数据）
const movie = ref({
  id: movieId.value,
  library_id: '',
  title: '',
  title_cn: '',
  year: undefined as number | undefined,
  genres: [] as string[],
  tags: [] as string[],
  rating: undefined as number | undefined,
  description_en: '',
  description_zh: '',
  backdrop: ''
})
const movieStore = useMovieStore()
const userStore = useUserStore()
const assetStore = useAssetStore()
const userAssetStore = useUserAssetsStore()
const collStore = useUserCollectionsStore()
const watchStore = useWatchHistoryStore()
const backdropUrl = ref<string>('')

const titleDisplay = computed(() => langView.value === 'user' ? (movie.value.title_cn || movie.value.title) : movie.value.title)
const descDisplay = computed(() => {
  if (langView.value === 'user') return movie.value.description_zh || movie.value.description_en
  return movie.value.description_en
})

const ratingValue = computed(() => {
  const r = movie.value.rating
  return typeof r === 'number' ? r : undefined
})
const filledStars = computed(() => {
  const r = ratingValue.value ?? 0
  const filled = Math.round(r / 2)
  return Math.max(0, Math.min(5, filled))
})
const starsText = computed(() => '★'.repeat(filledStars.value) + '☆'.repeat(5 - filledStars.value))
const ariaRatingLabel = computed(() => (ratingValue.value !== undefined ? `评分 ${filledStars.value}/5` : '暂无评分'))

const isFavorite = computed(() => movieStore.entities[movieId.value]?.is_favoriter === true)
const isWatchLater = computed(() => movieStore.entities[movieId.value]?.is_watchLater === true)

// 编辑 Modal
const showEdit = ref(false)
const draft = ref({
  title: movie.value.title,
  title_cn: movie.value.title_cn,
  directorsCsv: '',
  actorsCsv: '',
  description: '',
  description_zh: movie.value.description_zh,
  release_date: '',
  genres: movie.value.genres.join('/'),
  rating: undefined as number | undefined,
  tagsCsv: '',
  countryCsv: '',
  language: '',
  duration: undefined as number | undefined,
})
const posterUpload = ref<File | null>(null)
const backdropUpload = ref<File | null>(null)
function onPosterFileChange(e: Event) {
  const input = e.target as HTMLInputElement | null
  const file = input?.files?.[0] ?? null
  posterUpload.value = file
}
function onBackdropFileChange(e: Event) {
  const input = e.target as HTMLInputElement | null
  const file = input?.files?.[0] ?? null
  backdropUpload.value = file
}
function openEdit() {
  draft.value = {
    title: movie.value.title,
    title_cn: movie.value.title_cn,
    directorsCsv: '',
    actorsCsv: '',
    description: movie.value.description_en,
    description_zh: movie.value.description_zh,
    release_date: '',
    genres: movie.value.genres.join('/'),
    rating: movie.value.rating,
    tagsCsv: (movie.value.tags ?? []).join(', '),
    countryCsv: '',
    language: '',
    duration: undefined,
  }
  showEdit.value = true
  posterUpload.value = null
  backdropUpload.value = null
}
async function saveEdit() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  const patch = {
    library_id: movie.value.library_id,
    title: String(draft.value.title || '').trim(),
    title_cn: String(draft.value.title_cn || '').trim(),
    directors: String(draft.value.directorsCsv || '').split(',').map(s=>s.trim()).filter(Boolean),
    actors: String(draft.value.actorsCsv || '').split(',').map(s=>s.trim()).filter(Boolean),
    description: String(draft.value.description || '').trim(),
    description_cn: String(draft.value.description_zh || '').trim(),
    release_date: draft.value.release_date || null,
    genres: String(draft.value.genres || '').split('/').map(s=>s.trim()).filter(Boolean),
    rating: typeof draft.value.rating === 'number' ? draft.value.rating : undefined,
    tags: String(draft.value.tagsCsv || '').split(',').map(s=>s.trim()).filter(Boolean),
    metadata: {
      duration: typeof draft.value.duration === 'number' ? draft.value.duration : undefined,
      country: String(draft.value.countryCsv || '').split(',').map(s=>s.trim()).filter(Boolean),
      language: String(draft.value.language || '') || undefined,
    },
  }
  try {
    await movieStore.update(token, movieId.value, patch)
    const files: File[] = []
    const types: Array<'poster'|'backdrop'> = []
    if (posterUpload.value) { files.push(posterUpload.value); types.push('poster') }
    if (backdropUpload.value) { files.push(backdropUpload.value); types.push('backdrop') }
    if (files.length > 0) {
      await moviesApi.uploadMovieImages(token, movieId.value, files, types)
      const urls = await movieStore.getCoversSigned(token, [movieId.value], 'backdrop.jpg')
      backdropUrl.value = urls?.[0] ?? ''
      movie.value.backdrop = backdropUrl.value
    }
    showEdit.value = false
    ElMessage.success('影片元数据已更新')
  } catch (e: any) { ElMessage.error(String(e?.message ?? e)) }
}

// 固定背景亮度：移除滚动联动，固定透明度
const heroFade = ref(1)
const heroImageReady = ref(false)

// 演职员表（占位，后续接入）
const casts = ref<Array<{ id: string; name_cn: string; name_en: string; role: string; avatar?: string }>>([])
const castEl = ref<HTMLElement | null>(null)

// 影片资产区
type MovieAssetTab = 'media' | 'subtitle' | 'image'
const movieTab = ref<MovieAssetTab>('media')
const movieView = ref<'card'|'table'>('card')
function formatMinutes(seconds?: number | null): string {
  const s = typeof seconds === 'number' ? seconds : 0
  if (s <= 0) return '0 分钟'
  if (s < 60) return '<1 分钟'
  const m = Math.round(s / 60)
  return `${m} 分钟`
}
function formatSize(bytes?: number | null): string {
  const b = typeof bytes === 'number' ? bytes : 0
  if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(1)}GB`
  if (b >= 1024 ** 2) return `${Math.round(b / 1024 ** 2)}MB`
  if (b >= 1024) return `${Math.round(b / 1024)}KB`
  return `${b}B`
}
function qualityToLabel(q?: string | null): string {
  const v = (q || '').toLowerCase()
  if (v === '2160p') return '4K'
  if (v === '1440p') return '2K'
  if (v === '1080p') return '1080P'
  if (v === '720p') return '720P'
  if (v === 'sd') return 'SD'
  return v.toUpperCase()
}
function qualityClass(q?: string | null): string {
  const v = (q || '').toLowerCase()
  if (v === '2160p') return 'res-4k'
  if (v === '1080p') return 'res-1080p'
  if (v === '720p') return 'res-720p'
  return 'res-sd'
}
const mediaAssets = computed(() => assetStore.list.filter(a => a.type === AssetType.VIDEO && !a.is_deleted).map(a => {
  const md = (a.metadata as AssetMeta) || {}
  const durationMin = formatMinutes(md.duration)
  const resolutionLabel = qualityToLabel(md.quality)
  const resolutionClass = qualityClass(md.quality)
  const sizePretty = formatSize(md.size)
  return {
    id: a.id,
    name: a.name,
    durationMin,
    resolutionLabel,
    resolutionClass,
    sizePretty,
    tags: (a.tags || []) as string[],
    url: thumbMapMovie.value[a.id] ?? '',
    meta: (md.width && md.height) ? `${md.width}x${md.height}` : '',
    raw: a,
  }
}))
const subtitleAssets = computed(() => assetStore.list.filter(a => a.type === AssetType.SUBTITLE && !a.is_deleted).map(a => {
  const md = (a.metadata as AssetMeta) || {}
  return {
    id: a.id,
    name: a.name,
    size: String(md.size ?? ''),
    language: md.language ?? '',
    tags: (a.tags || []) as string[],
    raw: a,
  }
}))
const thumbMapMovie = ref<Record<string, string>>({})
const imageAssets = computed(() => assetStore.list.filter(a => a.type === AssetType.IMAGE && !a.is_deleted).map(a => {
  const md = (a.metadata as AssetMeta) || {}
  return {
    id: a.id,
    name: a.name,
    size: String(md.size ?? ''),
    tags: (a.tags || []) as string[],
    meta: (md.width && md.height) ? `${md.width}x${md.height}` : '',
    url: thumbMapMovie.value[a.id] ?? '',
    raw: a,
  }
}))

// 用户资产区
type UserAssetTab = 'clip' | 'screenshot' | 'note' | 'comment'
const userTab = ref<UserAssetTab>('clip')
const userView = ref<'card'|'table'>('card')
const showPublic = ref<boolean>(true)
const currentUserId = computed(() => userStore.user?.id ?? '')
const userAssetsCombined = ref<UserAssetRead[]>([])
const thumbMapUser = ref<Record<string, string>>({})
const userNameMap = ref<Record<string, string>>({})

function getUserName(userId: string): string {
  return userNameMap.value[userId] || userId
}

function canEditAsset(assetUserId: string): boolean {
  if (!userStore.user) return false
  if (userStore.hasRole(UserRole.ADMIN)) return true
  return userStore.user.id === assetUserId
}

function formatResolution(meta: AssetMeta | unknown): string {
  const m = meta as AssetMeta
  if (m?.width && m?.height) {
    return `${m.width}x${m.height}`
  }
  return qualityToLabel(m?.quality)
}

function formatTime(iso?: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

const clips = computed(() => userAssetsCombined.value.filter(a => a.type === UserAssetType.CLIP && (
  showPublic.value ? (a.user_id === currentUserId.value || a.is_public) : (a.user_id === currentUserId.value)
)).map(a => ({
  id: a.id,
  name: a.name,
  user: getUserName(a.user_id),
  userId: a.user_id,
  tags: a.tags,
  desc: a.content ?? '',
  meta: typeof (a.metadata as AssetMeta)?.duration === 'number' ? formatMinutes((a.metadata as AssetMeta).duration) : '',
  url: thumbMapUser.value[a.id] ?? '',
  raw: a,
  size: formatSize((a.metadata as AssetMeta)?.size),
  resolution: formatResolution(a.metadata)
})))
const screenshots = computed(() => userAssetsCombined.value.filter(a => a.type === UserAssetType.SCREENSHOT && (
  showPublic.value ? (a.user_id === currentUserId.value || a.is_public) : (a.user_id === currentUserId.value)
)).map(a => ({
  id: a.id,
  name: a.name,
  user: getUserName(a.user_id),
  userId: a.user_id,
  tags: a.tags,
  desc: a.content ?? '',
  meta: (((a.metadata as AssetMeta)?.width && (a.metadata as AssetMeta)?.height) ? `${(a.metadata as AssetMeta).width}x${(a.metadata as AssetMeta).height}` : ''),
  url: thumbMapUser.value[a.id] ?? '',
  raw: a,
  size: formatSize((a.metadata as AssetMeta)?.size)
})))
const notes = computed(() => userAssetsCombined.value.filter(a => a.type === UserAssetType.NOTE && (
  showPublic.value ? (a.user_id === currentUserId.value || a.is_public) : (a.user_id === currentUserId.value)
)).map(a => ({
  id: a.id,
  name: a.name,
  user: getUserName(a.user_id),
  userId: a.user_id,
  summary: a.content ?? '',
  raw: a,
  tags: a.tags
})))
const comments = computed(() => userAssetsCombined.value.filter(a => a.type === UserAssetType.REVIEW && (
  showPublic.value ? (a.user_id === currentUserId.value || a.is_public) : (a.user_id === currentUserId.value)
)).map(a => ({
  id: a.id,
  user: getUserName(a.user_id),
  userId: a.user_id,
  content: a.content ?? '',
  time: formatTime(a.updated_at || a.created_at),
  raw: a
})))

// 操作响应
function onPlay() {
  const first = assetStore.list.find(a => a.type === AssetType.VIDEO)
  if (first) {
    playAsset(first.id)
  } else {
    ElMessage.warning('暂无本地媒体资源，无法播放')
  }
}
async function onComplete() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  const first = assetStore.list.find(a => a.type === AssetType.VIDEO)
  if (!first) { ElMessage.warning('当前电影无视频资产以供播放'); return }
  const duration = (first.metadata as AssetMeta)?.duration ?? null
  try {
    await watchStore.updateProgress(token, {
      movie_id: movieId.value,
      asset_id: first.id,
      type: WatchType.Official,
      last_position: duration ?? 0,
      total_duration: duration ?? null,
    })
    ElMessage.success('已记录完播')
  } catch (e: any) {
    ElMessage.error(String(e?.message ?? '记录完播失败'))
  }
}
function onToggleFavorite() { movieStore.toggleFavorite(movieId.value) }
function onToggleWatchLater() { movieStore.toggleWatchLater(movieId.value) }
const showAddListDialog = ref(false)
const selectedCollectionIds = ref<string[]>([])
const creatingList = ref(false)
const createListForm = ref<{ name: string; description?: string; is_public: boolean }>({ name: '', description: '', is_public: true })
const myCollections = computed(() => collStore.customlists.filter((c) => c.user_id === currentUserId.value))
async function openAddToListDialog() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await collStore.fetchList(token) } catch {}
  showAddListDialog.value = true
}
async function submitAddToList() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  const ids = selectedCollectionIds.value.slice()
  if (ids.length === 0) { ElMessage.warning('请选择片单'); return }
  try {
    for (const cid of ids) { await collStore.addMovies(token, cid, [movieId.value]) }
    ElMessage.success('已加入片单')
    showAddListDialog.value = false
    selectedCollectionIds.value = []
  } catch (e: any) { ElMessage.error(String(e?.message ?? e)) }
}
async function submitCreateList() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  if (!createListForm.value.name || createListForm.value.name.trim().length === 0) { ElMessage.warning('片单名称为必填项'); return }
  creatingList.value = true
  try {
    await collStore.create(token, { name: createListForm.value.name, description: createListForm.value.description ?? '', is_public: createListForm.value.is_public, movies: [], type: CustomListType.CUSTOMLIST })
    await collStore.fetchList(token)
    ElMessage.success('已创建片单')
    createListForm.value = { name: '', description: '', is_public: true }
  } catch (e: any) { ElMessage.error(String(e?.message ?? e)) } finally { creatingList.value = false }
}

function gotoCreateList() {
  router.push({ name: 'lists', query: { create: '1' } })
}



const showAddMovieAssetDialog = ref(false)
const submitting = ref(false)
const addMovieAssetForm = ref<{ type: AssetType; source: 'file' | 'url' | 'local_path'; name?: string; file?: File | null; url?: string; local_path?: string }>({ type: AssetType.VIDEO, source: 'file', name: '', file: null, url: '', local_path: '' })

// 自动解析名称辅助函数
function extractName(input: File | string | null | undefined): string {
  if (!input) return ''
  let filename = ''
  if (input instanceof File) {
    filename = input.name
  } else if (typeof input === 'string') {
    const parts = input.split('?')[0]?.split('#')
    let cleanPath = parts ? parts[0] : input
    if (cleanPath) {
      cleanPath = cleanPath.replace(/\\/g, '/')
      filename = cleanPath.split('/').pop() ?? ''
    }
  }
  
  if (!filename) return ''
  
  const lastDotIndex = filename.lastIndexOf('.')
  if (lastDotIndex <= 0) return filename
  return filename.substring(0, lastDotIndex)
}

// 监听官方资产表单源变化，自动填充名称
watch(() => addMovieAssetForm.value.file, (val) => {
  if (val && addMovieAssetForm.value.source === 'file') {
    addMovieAssetForm.value.name = extractName(val)
  }
})
watch(() => addMovieAssetForm.value.url, (val) => {
  if (val && addMovieAssetForm.value.source === 'url') {
    addMovieAssetForm.value.name = extractName(val)
  }
})
watch(() => addMovieAssetForm.value.local_path, (val) => {
  if (val && addMovieAssetForm.value.source === 'local_path') {
    addMovieAssetForm.value.name = extractName(val)
  }
})

function mapMovieTabToType(t: MovieAssetTab): AssetType { return t === 'media' ? AssetType.VIDEO : (t === 'subtitle' ? AssetType.SUBTITLE : AssetType.IMAGE) }
function onAddMovieAsset() {
  addMovieAssetForm.value.type = mapMovieTabToType(movieTab.value)
  addMovieAssetForm.value.source = 'file'
  addMovieAssetForm.value.name = ''
  addMovieAssetForm.value.file = null
  addMovieAssetForm.value.url = ''
  addMovieAssetForm.value.local_path = ''
  showAddMovieAssetDialog.value = true
}
async function submitAddMovieAsset() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  const f = addMovieAssetForm.value
  if (!f.name || !f.name.trim()) { ElMessage.warning('请输入名称'); return }
  submitting.value = true
  try {
    if (f.source === 'file') {
      if (!f.file) { ElMessage.warning('请选择文件'); submitting.value = false; return }
      await assetStore.uploadFile(token, movieId.value, { type: f.type, name: f.name || null }, f.file)
    } else if (f.source === 'url') {
      if (!f.url || !f.url.trim()) { ElMessage.warning('请输入 URL'); submitting.value = false; return }
      await assetStore.importFromUrl(token, movieId.value, { type: f.type, url: f.url.trim(), name: f.name || null })
    } else {
      if (!f.local_path || !f.local_path.trim()) { ElMessage.warning('请输入本地路径'); submitting.value = false; return }
      await assetStore.importFromLocal(token, movieId.value, { type: f.type, src_path: f.local_path.trim(), name: f.name || null })
    }
    showAddMovieAssetDialog.value = false
    await loadAssets()
    ElMessage.success('已添加影片资产')
  } catch (e: any) { ElMessage.error(String(e?.message ?? e)) } finally { submitting.value = false }
}

const showAddUserAssetDialog = ref(false)
const addUserAssetForm = ref<{ type: UserAssetType; source: 'file' | 'local_path' | 'from_video'; name?: string; is_public: boolean; content?: string; file?: File | null; local_path?: string; asset_id?: string; time?: number }>({ type: UserAssetType.CLIP, source: 'file', name: '', is_public: true, content: '', file: null, local_path: '', asset_id: '', time: 0 })

// 监听用户资产表单源变化，自动填充名称
watch(() => addUserAssetForm.value.file, (val) => {
  if (val && addUserAssetForm.value.source === 'file') {
    addUserAssetForm.value.name = extractName(val)
  }
})
watch(() => addUserAssetForm.value.local_path, (val) => {
  if (val && addUserAssetForm.value.source === 'local_path') {
    addUserAssetForm.value.name = extractName(val)
  }
})

function mapUserTabToType(t: UserAssetTab): UserAssetType { return t === 'clip' ? UserAssetType.CLIP : (t === 'screenshot' ? UserAssetType.SCREENSHOT : (t === 'note' ? UserAssetType.NOTE : UserAssetType.REVIEW)) }
function onAddUserAsset() {
  addUserAssetForm.value.type = mapUserTabToType(userTab.value)
  addUserAssetForm.value.source = 'file'
  addUserAssetForm.value.name = ''
  addUserAssetForm.value.is_public = true
  addUserAssetForm.value.content = ''
  addUserAssetForm.value.file = null
  addUserAssetForm.value.local_path = ''
  addUserAssetForm.value.asset_id = ''
  addUserAssetForm.value.time = 0
  showAddUserAssetDialog.value = true
}
const videoAssetOptions = computed(() => assetStore.list.filter(a => a.type === AssetType.VIDEO).map(a => ({ id: a.id, name: a.name })))
async function submitAddUserAsset() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  const f = addUserAssetForm.value
  try {
    if (f.type === UserAssetType.NOTE || f.type === UserAssetType.REVIEW) {
      if (!f.content || !f.content.trim()) { ElMessage.warning('请输入内容'); return }
      await userAssetStore.createText(token, { movie_id: movieId.value, type: f.type, name: f.name || null, is_public: f.is_public, content: f.content.trim() })
    } else {
      if (f.source === 'file') {
        if (!f.file) { ElMessage.warning('请选择文件'); return }
        await userAssetStore.upload(token, { movie_id: movieId.value, type: f.type, name: f.name || null, is_public: f.is_public, file: f.file })
      } else {
        if (!f.local_path || !f.local_path.trim()) { ElMessage.warning('请输入本地路径'); return }
        await userAssetStore.upload(token, { movie_id: movieId.value, type: f.type, name: f.name || null, is_public: f.is_public, local_path: f.local_path.trim() })
      }
    }
    showAddUserAssetDialog.value = false
    await loadUserAssets()
    ElMessage.success('已添加用户资产')
  } catch (e: any) { ElMessage.error(String(e?.message ?? e)) }
}

async function playAsset(assetId: string, start = 0, source: 'official' | 'user' = 'official') {
  const mid = movieId.value
  if (!mid) { ElMessage.error('影片不存在'); return }
  await router.push({ name: 'player', params: { id: mid }, query: { asset_id: assetId, start, source } })
}

import { ElMessageBox } from 'element-plus'
const showEditAssetDialog = ref(false)
const editAssetForm = ref<{ id: string; name: string; tagsCsv: string }>({ id: '', name: '', tagsCsv: '' })

function openEditAsset(id: string, name: string, tags: string[] = []) {
  editAssetForm.value = {
    id,
    name,
    tagsCsv: tags.join(', ')
  }
  showEditAssetDialog.value = true
}

async function submitEditAsset() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  const { id, name, tagsCsv } = editAssetForm.value
  const tags = tagsCsv.split(',').map(s => s.trim()).filter(Boolean)
  try {
    await assetStore.update(token, movieId.value, id, { name, tags })
    ElMessage.success('已更新资产')
    showEditAssetDialog.value = false
    await loadAssets()
  } catch (e: any) { ElMessage.error(String(e?.message ?? e)) }
}

async function deleteAsset(assetId: string) {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) { ElMessage.error('未登录'); return }
  try {
    await ElMessageBox.confirm('确认删除该资产？此操作为软删除，可恢复', '删除确认', { type: 'warning' })
    await assetStore.remove(token, movieId.value, assetId, true)
    ElMessage.success('已删除资产')
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(String(e?.message ?? e))
    }
  }
}

async function deleteUserAsset(assetId: string) {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try {
    await ElMessageBox.confirm('确认删除该用户资产？', '删除确认', { type: 'warning' })
    await userAssetStore.remove(token, assetId)
    await loadUserAssets()
    ElMessage.success('已删除资产')
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(String(e?.message ?? e))
    }
  }
}

const showNoteViewer = ref(false)
const noteContent = ref('')
function viewNote(content: string) {
  noteContent.value = content
  showNoteViewer.value = true
}

const showEditUserAssetDialog = ref(false)
const editUserAssetForm = ref<{ id: string; type: UserAssetType; name: string; content: string; tagsCsv: string; is_public: boolean }>({
  id: '',
  type: UserAssetType.CLIP,
  name: '',
  content: '',
  tagsCsv: '',
  is_public: false
})

function openEditUserAsset(asset: UserAssetRead) {
  editUserAssetForm.value = {
    id: asset.id,
    type: asset.type,
    name: asset.name,
    content: asset.content ?? '',
    tagsCsv: (asset.tags || []).join(', '),
    is_public: asset.is_public
  }
  showEditUserAssetDialog.value = true
}

import type { UserAssetUpdateRequestSchema } from '@/types/user_asset'

async function submitEditUserAsset() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  const { id, type, name, content, tagsCsv, is_public } = editUserAssetForm.value
  const tags = tagsCsv.split(',').map(s => s.trim()).filter(Boolean)
  try {
    // 1. 更新基本信息
    const patch: UserAssetUpdateRequestSchema = { name }
    if (type !== UserAssetType.REVIEW) {
      patch.tags = tags
    }
    if (type === UserAssetType.NOTE || type === UserAssetType.REVIEW) {
      patch.content = content
    }
    await userAssetStore.update(token, id, patch)
    
    // 2. 更新公开状态 (如果变更)
    // 注意：当前 API 可能不支持在 update 中直接更新 is_public，需检查后端接口或使用专用接口
    // 假设 userAssetStore.setPublic 可用
    const current = userAssetsCombined.value.find(a => a.id === id)
    if (current && current.is_public !== is_public) {
      await userAssetStore.setPublic(token, id, is_public)
    }

    ElMessage.success('用户资产已更新')
    showEditUserAssetDialog.value = false
    await loadUserAssets()
  } catch (e: any) {
    ElMessage.error(String(e?.message ?? e))
  }
}

// 视图文案
const movieTabLabel = (t: MovieAssetTab) => t === 'media' ? '媒体' : (t === 'subtitle' ? '字幕' : '图片')
const userTabLabel = (t: UserAssetTab) => ({ clip: '剪辑', screenshot: '截图', note: '笔记', comment: '评论' }[t])

// 数据加载
async function loadMovie() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) return
  try {
    const m = await movieStore.fetchById(token, movieId.value)
    movie.value.id = m.id
    movie.value.library_id = m.library_id
    movie.value.title = m.title
    movie.value.title_cn = m.title_cn
    movie.value.genres = m.genres
    movie.value.tags = m.tags
    movie.value.rating = m.rating ?? undefined
    movie.value.year = m.release_date ? Number(String(m.release_date).slice(0,4)) : undefined
    movie.value.description_en = m.description
    movie.value.description_zh = m.description_cn
    const urls = await movieStore.getCoversSigned(token, [m.id], 'backdrop.jpg')
    backdropUrl.value = urls?.[0] ?? ''
    movie.value.backdrop = backdropUrl.value
  } catch { /* noop */ }
}

async function loadAssets() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) return
  try {
    await assetStore.fetchAssets(token, movieId.value)
    const ids = assetStore.list.filter(a => !a.is_deleted && (a.type === AssetType.IMAGE || (a.type === AssetType.VIDEO && (a.metadata as AssetMeta)?.quality))).map(a => a.id)
    if (ids.length > 0) {
      const urls = await movieAssets.getAssetThumbnailsSigned(token, ids)
      const map: Record<string, string> = {}
      ids.forEach((id, i) => { map[id] = urls[i] ?? '' })
      thumbMapMovie.value = map
    } else {
      thumbMapMovie.value = {}
    }
  } catch {}
}

async function loadUserAssets() {
  const token = userStore.token ?? ''
  if (!token || !movieId.value) return
  try {
    let items: UserAssetRead[] = []
    if (showPublic.value) {
      const own = await userAssets.listUserAssets(token, { movie_ids: [movieId.value], page: 1, size: 20 })
      const pub = await userAssets.listUserAssets(token, { movie_ids: [movieId.value], page: 1, size: 20, is_public: true })
      const ownItems: UserAssetRead[] = (own as any).items ?? []
      const pubItems: UserAssetRead[] = (pub as any).items ?? []
      const merged: Record<string, UserAssetRead> = {}
      for (const a of ownItems) merged[a.id] = a
      for (const a of pubItems) merged[a.id] = a
      items = Object.values(merged)
    } else {
      const own = await userAssets.listUserAssets(token, { movie_ids: [movieId.value], page: 1, size: 20 })
      items = ((own as any).items ?? []) as UserAssetRead[]
    }
    userAssetsCombined.value = items

    // 批量获取用户名
    const userIds = Array.from(new Set(items.map(a => a.user_id)))
    if (userIds.length > 0) {
      const map = await usersApi.getUserMapping(token, userIds)
      userNameMap.value = { ...userNameMap.value, ...map }
    }

    const shotIds = userAssetsCombined.value.filter(a => 
      (a.type === UserAssetType.SCREENSHOT) || 
      (a.type === UserAssetType.CLIP && (a.metadata as AssetMeta)?.quality)
    ).map(a => a.id)
    if (shotIds.length > 0) {
      const urls = await userAssets.getUserAssetThumbnailsSigned(token, shotIds)
      const map: Record<string, string> = {}
      shotIds.forEach((id, i) => { map[id] = urls[i] ?? '' })
      thumbMapUser.value = map
    } else {
      thumbMapUser.value = {}
    }
  } catch {}
}

onMounted(async () => {
  await loadMovie()
  await loadAssets()
  await loadUserAssets()
})

watch(() => movie.value.backdrop, (url) => {
  if (!url) return
  const img = new Image()
  img.onload = () => { heroFade.value = 1; heroImageReady.value = true }
  img.src = url
})

watch(showPublic, async () => { await loadUserAssets() })

const showImageViewer = ref(false)
const viewerUrl = ref('')
const viewerTitle = ref('')
async function viewImage(assetId: string, type: 'movie' | 'user') {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try {
    let url = ''
    if (type === 'movie') {
      url = await movieAssets.getMovieAssetFile(token, assetId)
    } else {
      url = await userAssets.getUserAssetFile(token, assetId)
    }
    viewerUrl.value = url
    viewerTitle.value = '查看图片'
    showImageViewer.value = true
  } catch (e: any) {
    ElMessage.error(String(e?.message ?? e))
  }
}

const showJsonViewer = ref(false)
const jsonContent = ref('')

function openJsonViewer(data: unknown) {
  jsonContent.value = JSON.stringify(data, null, 2)
  showJsonViewer.value = true
}

// ----------------------------------------------------------------------
// 右键菜单
const showContextMenu = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)

const menuItems = computed<MenuItem[]>(() => [
  {
    label: langView.value === 'user' ? '切换到原文' : '切换到用户译文',
    // 拼接两个 path：Translate 图标
    icon: 'M12.87 15.07L10 12.2l.8-.8c.98 1.23 2.2 2.46 3.51 3.67-.5.34-1.02.66-1.44.99z M20 4H4c-1.1 0-2 .9-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6c0-1.1-.9-2-2-2zm-9.28 9.02l-1.5-1.5 2.3-2.3H7.5V7.5h5.5v1.5l-2.28 2.52zm6.03 3.48l-1.1-2.5h-3.3l-1.1 2.5h-1.7l3.25-7.5h1.7l3.25 7.5h-1.7z',
    action: () => { langView.value = langView.value === 'user' ? 'origin' : 'user' }
  },
  {
    label: '编辑影片元数据',
    // 拼接两个 path：Edit 图标
    icon: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25z M20.71 7.04a1.003 1.003 0 0 0 0-1.42l-2.34-2.34a1.003 1.003 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.84-1.82z',
    action: openEdit
  },
  { divider: true, label: '' },
  {
    label: '播放',
    icon: 'M8 5v14l11-7-11-7z',
    action: onPlay
  },
  {
    label: '标记为完播',
    icon: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zm0 12a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z',
    action: onComplete
  },
  {
    label: isFavorite.value ? '取消收藏' : '收藏',
    icon: 'M12 17.27L18.18 21 16.54 13.97 22 9.24l-7.19-.62L12 2 9.19 8.62 2 9.24l5.46 4.73L5.82 21z',
    // checked: isFavorite.value, // 上下文菜单通常用文字区分状态，或者用 checkmark
    action: onToggleFavorite
  },
  {
    label: isWatchLater.value ? '移出待看' : '稍后观看',
    // 拼接两个 path：WatchLater 图标
    icon: 'M12 8v5l4.3 2.58.7-1.16-3.5-2.09V8z M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z',
    // checked: isWatchLater.value,
    action: onToggleWatchLater
  },
  {
    label: '加入片单',
    icon: 'M19 13H5v-2h14v2zm-6 8H7a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h10a2 2 0 0 1 2 2v6h-2V5H7v14h6v2zm8-6v2h-2v2h-2v-2h-2v-2h2v-2h2v2h2z',
    action: openAddToListDialog
  }
])

function onContextMenu(e: MouseEvent) {
  contextMenuX.value = e.clientX
  contextMenuY.value = e.clientY
  showContextMenu.value = true
}
</script>

<template>
  <div class="movie-detail-page">
    <!-- Hero：背板背景 + 信息区（右上统一操作区） -->
    <section class="hero" :style="{ backgroundImage: `url(${movie.backdrop})`, '--fade': String(heroFade) } as any" @contextmenu.prevent="onContextMenu">
      <div class="hero__overlay" />
      <div class="hero__content">
        <div class="hero__info">
          <h1 class="title">{{ titleDisplay }}</h1>
          <p class="meta">
            <span v-if="movie.year">{{ movie.year }}</span>
            <span v-if="movie.genres?.length"> · {{ movie.genres.join(' / ') }}</span>
            <span v-if="movie.tags?.length"> · 标签：{{ movie.tags.join('、') }}</span>
          </p>
          <p class="rating" :aria-label="ariaRatingLabel">{{ starsText }} <span v-if="ratingValue !== undefined">{{ ratingValue }}</span><span v-else>暂无评分</span></p>
          <p class="desc">{{ descDisplay }}</p>
        </div>
  </div>
</section>

    <!-- Cast：水平滚动（移除左右箭头） -->
    <section class="cast">
      <div class="cast__header">
        <h2>演职员表</h2>
        <div class="spacer"></div>
      </div>
      <div class="cast__scroller" ref="castEl">
        <div v-for="c in casts" :key="c.id" class="cast__item">
          <div class="avatar">
            <img v-if="c.avatar" :src="c.avatar" :alt="c.name_en" />
            <div v-else class="avatar--placeholder">No Avatar</div>
          </div>
          <div class="name">{{ c.name_cn }} / {{ c.name_en }}</div>
          <div class="role">{{ c.role }}</div>
        </div>
      </div>
    </section>

    <!-- 影片资产区：分类切换 + 视图切换 + 添加 -->
    <section class="assets assets--movie">
      <div class="assets__header">
        <div class="tabs">
          <button
            v-for="t in ['media','subtitle','image']" :key="t"
            class="tabs__item"
            :class="{ 'tabs__item--active': movieTab===t }"
            @click="movieTab = t as MovieAssetTab"
          >{{ movieTabLabel(t as MovieAssetTab) }}</button>
        </div>
        <div class="cluster">
          <button class="icon-btn" title="切换视图" aria-label="切换视图" @click="movieView = (movieView==='card' ? 'table' : 'card')">
            <svg viewBox="0 0 24 24" :aria-label="movieView==='card' ? '卡片视图' : '表格视图'">
              <template v-if="movieView==='card'">
                <rect x="3" y="3" width="7" height="7" rx="2" />
                <rect x="14" y="3" width="7" height="7" rx="2" />
                <rect x="3" y="14" width="7" height="7" rx="2" />
                <rect x="14" y="14" width="7" height="7" rx="2" />
              </template>
              <template v-else>
                <rect x="3" y="3" width="18" height="4" rx="2" />
                <rect x="3" y="9" width="8" height="6" rx="2" />
                <rect x="13" y="9" width="8" height="6" rx="2" />
                <rect x="13" y="17" width="8" height="4" rx="2" />
              </template>
            </svg>
          </button>
          <button class="icon-btn" title="新增" aria-label="新增" @click="onAddMovieAsset">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="movieView==='card'" class="grid">
        <template v-if="movieTab==='media'">
          <div v-for="a in mediaAssets" :key="'media-' + a.id" class="asset-card type--media" tabindex="0">
            <div class="asset-card__thumb">
              <img v-if="a.url" :src="a.url" :alt="a.name" />
              <div v-else class="thumb__placeholder" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M4 6h16v12H4z"/><path d="M10 8v8l6-4-6-4z"/></svg>
              </div>
            </div>
            <div class="asset-card__panel">
              <div class="panel__title" :title="a.name">{{ a.name }}</div>
              <div class="panel__meta">时长：{{ a.durationMin }} · {{ a.meta || a.resolutionLabel }} · {{ a.sizePretty }}</div>
              <div class="panel__tags" v-if="a.tags?.length">
                <span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span>
              </div>
              <div class="panel__ops">
                <button class="btn btn--primary btn--sm" @click="playAsset(a.id, 0, 'official')">播放</button>
                <button class="btn btn--secondary btn--sm" @click="openEditAsset(a.id, a.name, a.tags)">编辑</button>
                <button class="btn btn--danger btn--sm" @click="deleteAsset(a.id)">删除</button>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="movieTab==='subtitle'">
          <div v-for="a in subtitleAssets" :key="'subtitle-' + a.id" class="card card--hover card--subtitle">
            <div class="card__title">{{ a.name }}</div>
            <div class="card__meta">大小：{{ formatSize(Number(a.size)) }}</div>
            <div class="card__ops">
              <button class="btn btn--secondary btn--sm" @click="openEditAsset(a.id, a.name, a.tags)">编辑</button>
              <button class="btn btn--danger btn--sm" @click="deleteAsset(a.id)">删除</button>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="a in imageAssets" :key="'image-' + a.id" class="asset-card type--image" tabindex="0">
            <div class="asset-card__thumb">
              <img v-if="a.url" :src="a.url" :alt="a.name" />
              <div v-else class="thumb__placeholder">No Image</div>
            </div>
            <div class="asset-card__panel">
              <div class="panel__title" :title="a.name">{{ a.name }}</div>
              <div class="panel__meta">大小：{{ a.size }} · {{ a.meta }}</div>
              <div class="panel__tags" v-if="a.tags?.length">
                <span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span>
              </div>
              <div class="panel__ops">
                <button class="btn btn--secondary btn--sm" @click="viewImage(a.id, 'movie')">查看</button>
                <button class="btn btn--secondary btn--sm" @click="openEditAsset(a.id, a.name, a.tags)">编辑</button>
                <button class="btn btn--danger btn--sm" @click="deleteAsset(a.id)">删除</button>
              </div>
            </div>
          </div>
        </template>
      </div>

      <table v-else class="table">
        <thead>
          <template v-if="movieTab==='media'">
            <tr>
              <th>名称</th>
              <th>时长</th>
              <th>分辨率</th>
              <th>大小</th>
              <th>标签</th>
              <th>操作</th>
            </tr>
          </template>
          <template v-else-if="movieTab==='subtitle'">
            <tr>
              <th>名称</th>
              <th>大小</th>
              <th>操作</th>
            </tr>
          </template>
          <template v-else>
            <tr>
              <th>名称</th>
              <th>大小</th>
              <th>分辨率</th>
              <th>标签</th>
              <th>操作</th>
            </tr>
          </template>
        </thead>
        <tbody>
          <template v-if="movieTab==='media'">
            <tr v-for="a in mediaAssets" :key="'media-' + a.id">
              <td>{{ a.name }}</td>
              <td>{{ a.durationMin }}</td>
              <td>{{ a.meta || a.resolutionLabel }}</td>
              <td>{{ a.sizePretty }}</td>
              <td><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></td>
              <td>
                <button class="btn btn--primary btn--sm" @click="playAsset(a.id, 0, 'official')">播放</button>
                <button class="btn btn--secondary btn--sm" @click="openEditAsset(a.id, a.name, a.tags)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button class="btn btn--danger btn--sm" @click="deleteAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
          <template v-else-if="movieTab==='subtitle'">
            <tr v-for="a in subtitleAssets" :key="'subtitle-' + a.id">
              <td>{{ a.name }}</td><td>{{ formatSize(Number(a.size)) }}</td>
              <td>
                <button class="btn btn--secondary btn--sm" @click="openEditAsset(a.id, a.name, a.tags)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button class="btn btn--danger btn--sm" @click="deleteAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="a in imageAssets" :key="'image-' + a.id">
              <td>{{ a.name }}</td><td>{{ formatSize(Number(a.size)) }}</td><td>{{ a.meta }}</td>
              <td><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></td>
              <td>
                <button class="btn btn--secondary btn--sm" @click="viewImage(a.id, 'movie')">查看</button>
                <button class="btn btn--secondary btn--sm" @click="openEditAsset(a.id, a.name, a.tags)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button class="btn btn--danger btn--sm" @click="deleteAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </section>

    <!-- 用户资产区：分类切换 + 视图切换 + 添加 + 公开开关 -->
    <section class="assets assets--user">
      <div class="assets__header">
        <div class="tabs">
          <button
            v-for="t in ['clip','screenshot','note','comment']" :key="t"
            class="tabs__item"
            :class="{ 'tabs__item--active': userTab===t }"
            @click="userTab = t as UserAssetTab"
          >{{ userTabLabel(t as UserAssetTab) }}</button>
        </div>
        <div class="cluster">
          <label class="switch">
            <input type="checkbox" v-model="showPublic" />
            <span>显示公开资产</span>
          </label>
          <button class="icon-btn" title="切换视图" aria-label="切换视图" @click="userView = (userView==='card' ? 'table' : 'card')">
            <svg viewBox="0 0 24 24" :aria-label="userView==='card' ? '卡片视图' : '表格视图'">
              <template v-if="userView==='card'">
                <rect x="3" y="3" width="7" height="7" rx="2" />
                <rect x="14" y="3" width="7" height="7" rx="2" />
                <rect x="3" y="14" width="7" height="7" rx="2" />
                <rect x="14" y="14" width="7" height="7" rx="2" />
              </template>
              <template v-else>
                <rect x="3" y="3" width="18" height="4" rx="2" />
                <rect x="3" y="9" width="8" height="6" rx="2" />
                <rect x="13" y="9" width="8" height="6" rx="2" />
                <rect x="13" y="17" width="8" height="4" rx="2" />
              </template>
            </svg>
          </button>
          <button class="icon-btn" title="新增" aria-label="新增" @click="onAddUserAsset">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="userView==='card'" class="grid">
        <template v-if="userTab==='clip'">
          <div v-for="a in clips" :key="'clip-' + a.id" class="asset-card type--clip" tabindex="0">
            <div class="asset-card__thumb">
              <img v-if="a.url" :src="a.url" :alt="a.name" style="object-fit:cover;width:100%;height:100%" />
              <div v-else class="thumb__placeholder" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M4 6h16v12H4z"/><path d="M10 8v8l6-4-6-4z"/></svg>
              </div>
            </div>
            <div class="asset-card__panel">
              <div class="panel__title" :title="a.name">{{ a.name }}</div>
              <div class="panel__meta">用户：{{ a.user }}</div>
              <div class="panel__meta">{{ a.meta }} · {{ a.resolution }} · {{ a.size }}</div>
              <div class="panel__tags" v-if="a.tags?.length"><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></div>
              <div class="panel__ops">
                <button class="btn btn--primary btn--sm" @click="playAsset(a.id, 0, 'user')">播放</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="userTab==='screenshot'">
          <div v-for="a in screenshots" :key="'shot-' + a.id" class="asset-card type--image" tabindex="0">
            <div class="asset-card__thumb">
              <img v-if="a.url" :src="a.url" :alt="a.name" />
              <div v-else class="thumb__placeholder">No Image</div>
            </div>
            <div class="asset-card__panel">
              <div class="panel__title" :title="a.name">{{ a.name }}</div>
              <div class="panel__meta">用户：{{ a.user }}</div>
              <div class="panel__meta">{{ a.size }} · {{ a.meta }}</div>
              <div class="panel__tags" v-if="a.tags?.length"><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></div>
              <div class="panel__ops">
                <button class="btn btn--secondary btn--sm" @click="viewImage(a.id, 'user')">查看</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
              </div>
            </div>
          </div>
        </template>
        <template v-else-if="userTab==='note'">
          <div v-for="a in notes" :key="'note-' + a.id" class="card card--hover card--subtitle">
            <div class="card__title" :title="a.name">{{ a.name }}</div>
            <div class="card__meta">用户：{{ a.user }}</div>
            <div class="card__ops">
              <button class="btn btn--secondary btn--sm" @click="viewNote(a.summary)">查看</button>
              <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
              <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="a in comments" :key="'comment-' + a.id" class="card card--hover">
            <el-tooltip :content="a.content" placement="top" :show-after="500">
              <div class="card__desc" style="display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;">{{ a.content }}</div>
            </el-tooltip>
            <div class="card__meta" style="margin-top: auto;">用户：{{ a.user }}</div>
            <div class="card__ops">
              <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
              <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
            </div>
          </div>
        </template>
      </div>

      <table v-else class="table">
        <thead>
          <template v-if="userTab==='clip'">
            <tr>
              <th>名称</th>
              <th>时长</th>
              <th>分辨率</th>
              <th>大小</th>
              <th>标签</th>
              <th>用户</th>
              <th>操作</th>
            </tr>
          </template>
          <template v-else-if="userTab==='screenshot'">
            <tr>
              <th>名称</th>
              <th>大小</th>
              <th>分辨率</th>
              <th>标签</th>
              <th>用户</th>
              <th>操作</th>
            </tr>
          </template>
          <template v-else-if="userTab==='note'">
            <tr>
              <th>名称</th>
              <th>用户</th>
              <th>标签</th>
              <th>描述</th>
              <th>操作</th>
            </tr>
          </template>
          <template v-else>
            <tr>
              <th>用户</th>
              <th>描述</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </template>
        </thead>
        <tbody>
          <template v-if="userTab==='clip'">
            <tr v-for="a in clips" :key="'clip-' + a.id">
              <td>{{ a.name }}</td>
              <td>{{ a.meta }}</td>
              <td>{{ a.resolution }}</td>
              <td>{{ a.size }}</td>
              <td><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></td>
              <td>{{ a.user }}</td>
              <td>
                <button class="btn btn--primary btn--sm" @click="playAsset(a.id, 0, 'user')">播放</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
          <template v-else-if="userTab==='screenshot'">
            <tr v-for="a in screenshots" :key="'shot-' + a.id">
              <td>{{ a.name }}</td>
              <td>{{ a.size }}</td>
              <td>{{ a.meta }}</td>
              <td><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></td>
              <td>{{ a.user }}</td>
              <td>
                <button class="btn btn--secondary btn--sm" @click="viewImage(a.id, 'user')">查看</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
          <template v-else-if="userTab==='note'">
            <tr v-for="a in notes" :key="'note-' + a.id">
              <td>{{ a.name }}</td>
              <td>{{ a.user }}</td>
              <td><span v-for="t in a.tags" :key="t" class="chip">{{ t }}</span></td>
              <td :title="a.summary" style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ a.summary }}</td>
              <td>
                <button class="btn btn--secondary btn--sm" @click="viewNote(a.summary)">查看</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
          <template v-else>
            <tr v-for="a in comments" :key="'comment-' + a.id">
              <td>{{ a.user }}</td>
              <td style="white-space: pre-wrap;">{{ a.content }}</td>
              <td>{{ a.time }}</td>
              <td>
                <button v-if="canEditAsset(a.userId)" class="btn btn--secondary btn--sm" @click="openEditUserAsset(a.raw)">编辑</button>
                <button class="btn btn--secondary btn--sm" @click="openJsonViewer(a.raw)">详情</button>
                <button v-if="canEditAsset(a.userId)" class="btn btn--danger btn--sm" @click="deleteUserAsset(a.id)">删除</button>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </section>

    <!-- Toast 容器 -->


    <!-- 编辑弹窗 Modal -->
    <div v-if="showEdit" class="modal__overlay" @click.self="showEdit=false">
      <div class="modal__content">
        <h3>编辑影片元数据</h3>
        <div class="form-grid">
          <label>原文标题<input class="input" v-model="draft.title" placeholder="原文标题" /></label>
          <label>用户译名<input class="input" v-model="draft.title_cn" placeholder="译名" /></label>
          <label>导演（, 分隔）<input class="input" v-model="draft.directorsCsv" placeholder="导演1, 导演2" /></label>
          <label>演员（, 分隔）<input class="input" v-model="draft.actorsCsv" placeholder="演员1, 演员2" /></label>
          <label>原文描述<textarea class="textarea" v-model="draft.description" rows="3" /></label>
          <label>中文描述<textarea class="textarea" v-model="draft.description_zh" rows="3" /></label>
          <label>上映日期<input class="input" v-model="draft.release_date" type="date" /></label>
          <label>类型（/ 分隔）<input class="input" v-model="draft.genres" placeholder="剧情/犯罪" /></label>
          <label>评分<input class="input" v-model.number="draft.rating" type="number" min="0" max="10" step="0.1" /></label>
          <label>标签（, 分隔）<input class="input" v-model="draft.tagsCsv" placeholder="惊悚, 经典" /></label>
          <label>国家/地区（, 分隔）<input class="input" v-model="draft.countryCsv" placeholder="中国, 美国" /></label>
          <label>语言<input class="input" v-model="draft.language" placeholder="zh/en" /></label>
          <label>时长（分钟）<input class="input" v-model.number="draft.duration" type="number" min="1" /></label>
          <label>封面（poster）<input type="file" accept="image/*" @change="onPosterFileChange" /></label>
          <label>背景图（backdrop）<input type="file" accept="image/*" @change="onBackdropFileChange" /></label>
        </div>
        <div class="modal__ops">
          <button class="btn btn--secondary" @click="showEdit=false">取消</button>
          <button class="btn btn--primary" @click="saveEdit">保存</button>
        </div>
      </div>
    </div>
  </div>
  <el-dialog v-model="showAddListDialog" title="添加到片单" width="560px">
    <div class="add-list-dialog">
      <div class="lists">
        <template v-if="myCollections.length > 0">
          <el-checkbox-group v-model="selectedCollectionIds">
            <el-checkbox v-for="c in myCollections" :key="c.id" :label="c.id">{{ c.name }}</el-checkbox>
          </el-checkbox-group>
        </template>
        <template v-else>
          <el-empty description="暂无片单">
            <el-button type="primary" @click="gotoCreateList">创建片单</el-button>
          </el-empty>
        </template>
      </div>
    </div>
    <template #footer>
      <el-button @click="gotoCreateList">创建片单</el-button>
      <el-button @click="showAddListDialog=false">取消</el-button>
      <el-button type="primary" @click="submitAddToList">确定</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="showImageViewer" title="查看图片" width="80%">
    <div style="display:flex;justify-content:center;align-items:center;max-height:70vh;overflow:auto">
      <img :src="viewerUrl" :alt="viewerTitle" style="max-width:100%;height:auto" />
    </div>
  </el-dialog>
  <el-dialog v-model="showAddMovieAssetDialog" title="添加影片资产" width="560px">
    <el-form class="el-reset" @submit.prevent>
      <el-form-item label="类型">
        <el-select v-model="addMovieAssetForm.type" placeholder="选择类型">
          <el-option :value="AssetType.VIDEO" label="媒体" />
          <el-option :value="AssetType.SUBTITLE" label="字幕" />
          <el-option :value="AssetType.IMAGE" label="图片" />
        </el-select>
      </el-form-item>
      <el-form-item label="来源">
        <el-radio-group v-model="addMovieAssetForm.source">
          <el-radio label="file">文件</el-radio>
          <el-radio label="url">URL</el-radio>
          <el-radio label="local_path">本地路径</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="名称">
        <el-input v-model="addMovieAssetForm.name" placeholder="必填" maxlength="128" show-word-limit />
      </el-form-item>
      <el-form-item v-if="addMovieAssetForm.source==='file'" label="文件">
        <input type="file" @change="(e:any)=>{ addMovieAssetForm.file = e?.target?.files?.[0] ?? null }" />
      </el-form-item>
      <el-form-item v-if="addMovieAssetForm.source==='url'" label="URL">
        <el-input v-model="addMovieAssetForm.url" placeholder="https://..." />
      </el-form-item>
      <el-form-item v-if="addMovieAssetForm.source==='local_path'" label="本地路径">
        <el-input v-model="addMovieAssetForm.local_path" placeholder="/path/to/file" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showAddMovieAssetDialog=false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitAddMovieAsset">确定</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="showAddUserAssetDialog" title="添加用户资产" width="640px">
    <el-form class="el-reset" @submit.prevent>
      <el-form-item label="类型">
        <el-select v-model="addUserAssetForm.type" placeholder="选择类型">
          <el-option :value="UserAssetType.CLIP" label="剪辑" />
          <el-option :value="UserAssetType.SCREENSHOT" label="截图" />
          <el-option :value="UserAssetType.NOTE" label="笔记" />
          <el-option :value="UserAssetType.REVIEW" label="评论" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="addUserAssetForm.type!==UserAssetType.NOTE && addUserAssetForm.type!==UserAssetType.REVIEW" label="来源">
        <el-radio-group v-model="addUserAssetForm.source">
          <el-radio label="file">文件</el-radio>
          <el-radio label="local_path">本地路径</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="addUserAssetForm.type!==UserAssetType.NOTE && addUserAssetForm.type!==UserAssetType.REVIEW" label="名称">
        <el-input v-model="addUserAssetForm.name" placeholder="可选" maxlength="128" show-word-limit />
      </el-form-item>
      <el-form-item label="公开">
        <el-switch v-model="addUserAssetForm.is_public" active-text="公开" inactive-text="私密" />
      </el-form-item>
      <el-form-item v-if="addUserAssetForm.type===UserAssetType.NOTE || addUserAssetForm.type===UserAssetType.REVIEW" label="内容">
        <el-input v-model="addUserAssetForm.content" type="textarea" :rows="4" placeholder="请输入内容" maxlength="1000" show-word-limit />
      </el-form-item>
      <el-form-item v-if="addUserAssetForm.source==='file' && addUserAssetForm.type!==UserAssetType.NOTE && addUserAssetForm.type!==UserAssetType.REVIEW" label="文件">
        <input type="file" @change="(e:any)=>{ addUserAssetForm.file = e?.target?.files?.[0] ?? null }" />
      </el-form-item>
      <el-form-item v-if="addUserAssetForm.source==='local_path' && addUserAssetForm.type!==UserAssetType.NOTE && addUserAssetForm.type!==UserAssetType.REVIEW" label="本地路径">
        <el-input v-model="addUserAssetForm.local_path" placeholder="/path/to/file" />
      </el-form-item>
      
    </el-form>
    <template #footer>
      <el-button @click="showAddUserAssetDialog=false">取消</el-button>
      <el-button type="primary" @click="submitAddUserAsset">确定</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="showEditAssetDialog" title="编辑资产" width="480px">
    <el-form class="el-reset" @submit.prevent>
      <el-form-item label="名称">
        <el-input v-model="editAssetForm.name" placeholder="资产名称" />
      </el-form-item>
      <el-form-item label="标签">
        <el-input v-model="editAssetForm.tagsCsv" placeholder="标签1, 标签2（请使用英文逗号分隔）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showEditAssetDialog=false">取消</el-button>
      <el-button type="primary" @click="submitEditAsset">保存</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="showEditUserAssetDialog" title="编辑用户资产" width="560px">
    <el-form class="el-reset" @submit.prevent>
      <el-form-item v-if="editUserAssetForm.type !== UserAssetType.REVIEW" label="名称">
        <el-input v-model="editUserAssetForm.name" placeholder="名称" />
      </el-form-item>
      <el-form-item v-if="editUserAssetForm.type === UserAssetType.NOTE || editUserAssetForm.type === UserAssetType.REVIEW" label="内容">
        <el-input v-model="editUserAssetForm.content" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item v-if="editUserAssetForm.type !== UserAssetType.REVIEW" label="标签">
        <el-input v-model="editUserAssetForm.tagsCsv" placeholder="标签1, 标签2" />
      </el-form-item>
      <el-form-item label="公开">
        <el-switch v-model="editUserAssetForm.is_public" active-text="公开" inactive-text="私密" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showEditUserAssetDialog=false">取消</el-button>
      <el-button type="primary" @click="submitEditUserAsset">保存</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="showJsonViewer" title="资产详情 (JSON)" width="640px">
    <pre style="background:var(--surface-2);padding:12px;border-radius:8px;overflow:auto;max-height:60vh;font-family:monospace;font-size:12px">{{ jsonContent }}</pre>
  </el-dialog>
  <el-dialog v-model="showNoteViewer" title="笔记内容" width="640px">
    <div style="background:var(--surface-2);padding:16px;border-radius:8px;overflow:auto;max-height:60vh;white-space: pre-wrap;line-height:1.6;">{{ noteContent }}</div>
  </el-dialog>
  <ContextMenu
    v-model:visible="showContextMenu"
    :x="contextMenuX"
    :y="contextMenuY"
    :items="menuItems"
  />
</template>

<style scoped>
/* 页面整体 */
.movie-detail-page { display: grid; gap: var(--space-5); padding-block: var(--space-5); }

/* Hero 背景与内容 */
.hero {
  position: relative;
  min-height: 68vh;
  background-position: center;
  background-size: cover;
  border-radius: var(--radius-lg);
  overflow: hidden;
  /* 统一信息区内边距为 20px（满足需求） */
  --content-pad: 20px;
}
.hero__overlay {
  position: absolute; inset: 0;
  /* 渐变透明度由主题变量控制，保证浅/深模式下文字对比 */
  background: linear-gradient(to bottom,
    color-mix(in oklab, var(--surface), black var(--hero-top, 32%)) 0%,
    color-mix(in oklab, var(--surface), black var(--hero-mid, 52%)) 38%,
    color-mix(in oklab, var(--surface), black var(--hero-bottom, 74%)) 100%);
  opacity: calc(1 - var(--fade, 0));
  transition: opacity var(--duration-medium) var(--ease);
}
.hero__content {
  position: absolute; inset: auto var(--content-pad) var(--content-pad) var(--content-pad);
  display: grid; grid-template-columns: 1fr; gap: var(--space-4);
  align-items: end;
}
.res-badge { display: inline-block; padding: 2px 6px; border-radius: 6px; line-height: 1; }
.res-4k { font-weight: 700; color: var(--brand); background: color-mix(in oklab, var(--brand), white 86%); }
.res-1080p { font-weight: 600; color: var(--text-primary); background: var(--surface-variant); }
.res-720p { font-weight: 500; color: var(--text-secondary); background: var(--surface-variant); }
.res-sd { font-weight: 500; color: var(--text-secondary); background: var(--surface); }
.hero__info { display: grid; gap: var(--space-2); color: var(--on-brand, white); }
.title { font-size: clamp(1.8rem, 3.6vw, 3.2rem); font-weight: 800; letter-spacing: 0.2px; color: var(--on-brand, #fff); text-shadow: 0 2px 22px rgba(0,0,0,0.45); }
.meta { color: color-mix(in oklab, var(--on-brand, #fff), black 25%); font-weight: 600; }
.rating { color: color-mix(in oklab, var(--brand), white 12%); font-weight: 700; }
.desc { color: color-mix(in oklab, var(--on-brand, #fff), black 15%); max-width: 80ch; }

/* Cast 水平滚动 */
.cast { padding-inline: var(--content-pad); display: grid; gap: var(--space-3); padding-block: var(--space-4); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-1); }
.cast__header { display: flex; align-items: center; gap: var(--space-3); }
.cast__header h2 { font-size: var(--text-lg); }
.cast__controls { display: flex; gap: 8px; }
.cast__scroller { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(160px, max-content); gap: var(--space-3); overflow-x: auto; padding-bottom: var(--space-2); scroll-snap-type: x mandatory; }
.cast__item { scroll-snap-align: start; background: color-mix(in oklab, var(--surface), var(--brand-weak) 8%); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--space-2); display: grid; gap: 6px; align-content: start; transition: transform var(--duration-fast) var(--ease), box-shadow var(--duration-fast) var(--ease); }
.cast__item:hover { transform: translateY(-2px) scale(1.02); box-shadow: var(--shadow-2); }
.avatar { border-radius: var(--radius); overflow: hidden; background: var(--surface-2); }
.avatar img { width: 100%; height: auto; display: block; }
.avatar--placeholder { display: grid; place-items: center; height: 88px; color: var(--text-muted); }
.name { font-weight: 700; color: var(--text-primary); }
.role { color: var(--text-secondary); }

/* 资产区 */
.assets { padding-inline: var(--content-pad); display: grid; gap: var(--space-3); padding-block: var(--space-4); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-1); }
.assets__header { display: flex; justify-content: space-between; align-items: center; }
  .cluster { display: inline-flex; align-items: center; gap: var(--space-2); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, 200px); gap: 16px; justify-content: start; }
  .chip { display: inline-block; padding: 2px 8px; border: 1px solid var(--border); border-radius: var(--radius-pill); color: var(--text-secondary); }

  /* 统一图标按钮风格（复用 icon-btn 样式） */
  .icon-btn { width: 34px; height: 34px; display: inline-grid; place-items: center; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); transition: background var(--duration-fast) var(--ease), transform var(--duration-fast) var(--ease), color var(--duration-fast) var(--ease); }
  .icon-btn:hover { background: color-mix(in oklab, var(--surface), var(--brand-weak) 14%); color: var(--text-primary); }
  .icon-btn:active { transform: translateY(1px); }
  .icon-btn svg { width: 18px; height: 18px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

/* 统一资产卡片交互：缩略图默认、悬停显示面板 */
.asset-card { position: relative; width: 200px; height: 300px; border-radius: 12px; overflow: hidden; background: var(--surface); border: 1px solid var(--border); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.asset-card__thumb { position: absolute; inset: 0; background: var(--surface-2); display: grid; place-items: center; }
.asset-card__thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb__placeholder { color: var(--text-muted); display: grid; place-items: center; width: 100%; height: 100%; }
.thumb__placeholder svg { width: 48px; height: 48px; fill: currentColor; }
.panel__title { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.panel__tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }
.panel__desc { color: rgba(255,255,255,0.7); margin-top: 6px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }

/* 优化资产卡片面板样式 */
.asset-card__panel {
  position: absolute; left: 0; right: 0; bottom: 0;
  padding: 12px;
  background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.8) 60%, transparent 100%);
  border-top: none;
  transform: translateY(100%); opacity: 0;
  transition: transform 300ms cubic-bezier(0.4, 0, 0.2, 1), opacity 300ms;
  display: flex; flex-direction: column; justify-content: flex-end;
  height: 100%; /* 覆盖整个卡片或部分 */
  pointer-events: none; /* 默认不阻挡点击 */
}
.asset-card:hover .asset-card__panel,
.asset-card:focus-within .asset-card__panel {
  transform: translateY(0); opacity: 1;
  pointer-events: auto;
}
.panel__title { color: white; text-shadow: 0 1px 2px rgba(0,0,0,0.8); }
.panel__meta { color: rgba(255,255,255,0.8); }
.panel__ops { margin-top: auto; padding-top: 8px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.panel__ops .btn { width: 100%; padding: 4px 0; justify-content: center; font-size: 12px; }

/* 字幕卡片背景 */
.card--subtitle {
  background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="%23999" stroke-width="1"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>');
  background-repeat: no-repeat;
  background-position: center 40%;
  background-size: 64px;
  min-height: 140px; /* 增加高度 */
  display: flex; flex-direction: column; justify-content: space-between;
}
.card--subtitle .card__ops { margin-top: auto; display: flex; gap: 8px; justify-content: flex-end; }

/* 表格优化 */
.table { table-layout: fixed; }
/* 名称列宽一点 */
.table th:nth-child(1), .table td:nth-child(1) { 
  width: 30%; 
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; 
}
.table td:nth-child(1):hover { overflow: visible; white-space: normal; position: relative; z-index: 10; background: var(--surface); box-shadow: var(--shadow-2); }
/* 操作列固定 */
.table th:last-child, .table td:last-child {
  position: sticky; right: 0;
  background: var(--surface);
  box-shadow: -2px 0 5px rgba(0,0,0,0.05);
  width: 220px; /* 增加宽度以容纳4个按钮 */
  text-align: center;
}
.table tr:hover td:last-child { background: var(--surface-2); }

/* Toast */
.toast-container { position: fixed; left: var(--content-pad); bottom: var(--content-pad); display: grid; gap: 8px; z-index: var(--z-toast); }
.toast { padding: 10px 14px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-2); color: var(--text-primary); }
.toast--success { border-color: color-mix(in oklab, var(--brand), black 18%); }
.toast--error { border-color: var(--danger); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(6px); }
.toast-enter-active, .toast-leave-active { transition: all 200ms var(--ease); }

/* Modal */
.modal__content {
  display: flex;
  flex-direction: column;
  max-height: 85vh;
  overflow: hidden;
}
.modal__content h3 {
  flex-shrink: 0;
  margin-bottom: var(--space-4);
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  overflow-y: auto;
  min-height: 0;
  padding-right: 4px;
}
.modal__ops {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
}

.form-grid .span-2 { grid-column: span 2; }
.add-list-dialog { display: flex; gap: 16px; }
.add-list-dialog .lists { flex: 1; max-height: 320px; overflow: auto; padding-right: 8px; }
.add-list-dialog :deep(.el-checkbox) { display: flex; align-items: center; padding: 8px 10px; border-radius: 8px; }
.add-list-dialog :deep(.el-checkbox + .el-checkbox) { margin-top: 6px; }
.add-list-dialog :deep(.el-empty__description) { color: var(--text-secondary); }

/* 响应式：小屏上下布局 */
@media (max-width: 900px) {
  .hero__content { grid-template-columns: 1fr; align-items: end; gap: var(--space-3); }
  .hero__right { order: 2; }
  .hero__left { order: 1; }
}

/* Hero 渐变强度在浅/深主题下调节，确保文字始终有足够对比 */
:global(html[data-theme="light"]) .hero { --hero-top: 38%; --hero-mid: 58%; --hero-bottom: 82%; }
:global(html[data-theme="dark"]) .hero { --hero-top: 28%; --hero-mid: 48%; --hero-bottom: 68%; }
</style>
