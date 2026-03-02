<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SortSelect from '@/components/ui/SortSelect.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { movies as moviesApi } from '@/api'
import { Picture, Edit, Delete } from '@element-plus/icons-vue'
import { useMovieStore } from '@/stores/movie'
import { useLibraryStore } from '@/stores/library'
import { useUserStore } from '@/stores/user'
import type { MovieCreateRequestSchema } from '@/types/movie'

// 路由参数：当前库 ID（用于后续接入真实数据）
const route = useRoute()
const router = useRouter()
const libraryId = computed(() => String(route.params.id ?? ''))

// 视图状态：搜索、视图模式、排序、过滤
const searchQuery = ref('')
const viewMode = ref<'card' | 'list' | 'gallery'>('card')
type SortKey = 'updated_at' | 'created_at' | 'title' | 'rating' | 'type'
const sortBy = ref<SortKey>('updated_at')
const sortOrder = ref<'asc' | 'desc'>('desc')

const onlyMe = ref<boolean>(false)
const onlyActive = ref<boolean>(false)
const typeFilter = ref<'all' | 'movie' | 'tv'>('all')
const showDeleted = ref<boolean>(false)

// 分页与后端对齐
const page = ref(1)
const pageSize = ref(24)

// 列表数据源：来自 store
const movieStore = useMovieStore()
const userStore = useUserStore()
const libraryStore = useLibraryStore()

// 过滤与排序
const filtered = computed(() => {
  const base = movieStore.list
  return base
})

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
    // 日期字符串优先；否则按数值/字典序
    const aTime = typeof av === 'string' && /\d{4}-\d{2}-\d{2}/.test(av) ? Date.parse(av) : av
    const bTime = typeof bv === 'string' && /\d{4}-\d{2}-\d{2}/.test(bv) ? Date.parse(bv) : bv
    if (aTime < bTime) return -1 * dir
    if (aTime > bTime) return 1 * dir
    return 0
  })
  return base
})

// 分页切片
const total = computed(() => movieStore.listMeta.total)
const rangeStart = computed(() => (total.value ? (page.value - 1) * pageSize.value + 1 : 0))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
const paged = computed(() => sorted.value)

// 交互回调（透传自 ListToolbar 与 PaginationBar）
function onRandom() {
  const arr = sorted.value
  if (!arr.length) return
  const pick = arr[Math.floor(Math.random() * arr.length)]
  console.log('随机进入媒体:', pick)
}
function onOpen(id: string | number) {
  router.push({ name: 'movie', params: { id } })
}
function onToggleView(mode: 'card' | 'list' | 'gallery') { viewMode.value = mode }
function onOpenSort() { showSort.value = !showSort.value }
function onOpenFilter() { showFilter.value = !showFilter.value }
async function onSearch(q: string) {
  searchQuery.value = q
  page.value = 1
  movieStore.setFilters({ query: q, page: 1, size: pageSize.value })
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await movieStore.fetchList(token); await refreshPosters() } catch { ElMessage.error('加载失败') }
}

// 过滤/排序面板开关
const showFilter = ref(false)
const showSort = ref(false)

// 将排序选择映射到本地 key；支持后续扩展 “最后访问”等
function mapSortBy(v: string) {
  switch (v) {
    case 'date': sortBy.value = 'updated_at'; break
    case 'title': sortBy.value = 'title'; break
    case 'rating': sortBy.value = 'rating'; break
    default: sortBy.value = 'updated_at'
  }
}

function updateSortOrder(v: string) {
  sortOrder.value = v === 'asc' ? 'asc' : 'desc'
}

// 分页事件
async function prevPage() {
  if (page.value > 1) {
    page.value -= 1
    movieStore.setPage(page.value)
    const token = userStore.token ?? ''
    if (!token) { ElMessage.error('未登录'); return }
    try { await movieStore.fetchList(token); await refreshPosters() } catch { ElMessage.error('加载失败') }
  }
}
async function nextPage() {
  const pageCount = Math.ceil(total.value / pageSize.value)
  if (page.value < pageCount) {
    page.value += 1
    movieStore.setPage(page.value)
    const token = userStore.token ?? ''
    if (!token) { ElMessage.error('未登录'); return }
    try { await movieStore.fetchList(token); await refreshPosters() } catch { ElMessage.error('加载失败') }
  }
}

const contextMenu = ref<{ visible: boolean; id: string | null; x: number; y: number }>({ visible: false, id: null, x: 0, y: 0 })
const virtualRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<any>(null)
const posterMap = ref<Record<string, string>>({})
async function refreshPosters() {
  const token = userStore.token ?? ''
  if (!token) return
  const ids = movieStore.list.map((m: any) => m.id)
  if (!ids.length) return
  try {
    const urls = await moviesApi.getMovieCoversSigned(token, ids, 'poster.jpg')
    const map: Record<string, string> = {}
    for (let i = 0; i < ids.length; i++) map[ids[i]] = urls[i]
    posterMap.value = { ...posterMap.value, ...map }
  } catch {}
}
function ensureVirtualRefAt(x: number, y: number): HTMLElement {
  let el = virtualRef.value
  if (!el) {
    el = document.createElement('span')
    el.style.position = 'absolute'
    el.style.width = '0px'
    el.style.height = '0px'
    el.style.pointerEvents = 'none'
    document.body.appendChild(el)
    virtualRef.value = el
  }
  el.style.left = `${x}px`
  el.style.top = `${y}px`
  return el
}
function onCardContextMenu(payload: { id: string; x: number; y: number }) {
  contextMenu.value = { visible: true, id: payload.id, x: payload.x, y: payload.y }
  const anchor = ensureVirtualRefAt(payload.x, payload.y)
  virtualRef.value = anchor
  dropdownRef.value?.handleOpen()
}

const showEdit = ref(false)
const defaultsEditForm = {
  title: '',
  title_cn: '',
  description: '',
  description_cn: '',
  release_date: '',
  directorsCsv: '',
  actorsCsv: '',
  genresCsv: '',
  tagsCsv: '',
  rating: null as number | null,
  duration: null as number | null,
  countryCsv: '',
  language: '',
}
const movieEditForm = ref({ ...defaultsEditForm })
function openEdit() {
  const id = contextMenu.value.id
  if (!id) return
  const m = movieStore.entities[id]
  if (!m) { showEdit.value = true; return }
  movieEditForm.value = {
    title: m.title ?? '',
    title_cn: m.title_cn ?? '',
    description: m.description ?? '',
    description_cn: m.description_cn ?? '',
    release_date: m.release_date ?? '',
    directorsCsv: (m.directors ?? []).join(', '),
    actorsCsv: (m.actors ?? []).join(', '),
    genresCsv: (m.genres ?? []).join(', '),
    tagsCsv: (m.tags ?? []).join(', '),
    rating: m.rating ?? null,
    duration: m.metadata?.duration ?? null,
    countryCsv: (m.metadata?.country ?? []).join(', '),
    language: m.metadata?.language ?? '',
  }
  showEdit.value = true
  contextMenu.value.visible = false
}
function splitCsv(v: string): string[] { return v.split(',').map(s => s.trim()).filter(Boolean) }
const canSubmitEdit = computed(() => movieEditForm.value.title.trim().length > 0)
async function submitEdit() {
  const token = userStore.token ?? ''
  const id = contextMenu.value.id
  if (!token || !id) { ElMessage.error('未登录'); return }
  const patch = {
    library_id: libraryId.value,
    title: movieEditForm.value.title.trim(),
    title_cn: movieEditForm.value.title_cn.trim(),
    directors: splitCsv(movieEditForm.value.directorsCsv),
    actors: splitCsv(movieEditForm.value.actorsCsv),
    description: movieEditForm.value.description.trim(),
    description_cn: movieEditForm.value.description_cn.trim(),
    release_date: movieEditForm.value.release_date ? movieEditForm.value.release_date : null,
    genres: splitCsv(movieEditForm.value.genresCsv),
    metadata: {
      duration: movieEditForm.value.duration ?? undefined,
      country: splitCsv(movieEditForm.value.countryCsv),
      language: movieEditForm.value.language || undefined,
    },
    rating: movieEditForm.value.rating ?? undefined,
    tags: splitCsv(movieEditForm.value.tagsCsv),
  }
  try {
    await movieStore.update(token, id, patch)
    ElMessage.success('电影信息已更新')
    showEdit.value = false
  } catch { ElMessage.error('更新失败') }
}

async function removeMovie() {
  const id = contextMenu.value.id
  const token = userStore.token ?? ''
  if (!id || !token) { ElMessage.error('未登录'); return }
  try {
    await ElMessageBox.confirm('删除后不可恢复，确认删除该电影？', '删除电影', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' })
    await movieStore.remove(token, id, true)
    ElMessage.success('电影已删除')
  } catch {}
  dropdownRef.value?.handleClose()
}

const posterFileInput = ref<HTMLInputElement | null>(null)
function changePoster() {
  const id = contextMenu.value.id
  if (!id) return
  posterFileInput.value?.click()
  contextMenu.value.visible = false
}
async function onPosterFileSelected(e: Event) {
  const input = e.target as HTMLInputElement | null
  const f = input?.files?.[0] ?? null
  if (input) input.value = ''
  const token = userStore.token ?? ''
  const id = contextMenu.value.id
  if (!token || !id || !f) { return }
  try {
    await moviesApi.uploadMoviePoster(token, id, f)
    const urls = await moviesApi.getMovieCoversSigned(token, [id], 'poster.jpg')
    posterMap.value = { ...posterMap.value, [id]: urls[0] ?? '' }
    ElMessage.success('封面已更新')
  } catch { ElMessage.error('封面更新失败') }
}

async function scrapeMetadata() {
  const token = userStore.token ?? ''
  const id = contextMenu.value.id
  if (!token || !id) { ElMessage.error('未登录'); return }
  try {
    const task = await moviesApi.scrapeMovieMetadata(token, id)
    ElMessage.success('已启动元数据爬取：' + (task.id ?? ''))
    dropdownRef.value?.handleClose()
  } catch { ElMessage.error('启动失败') }
}

async function scrapeSubtitles() {
  const token = userStore.token ?? ''
  const id = contextMenu.value.id
  if (!token || !id) { ElMessage.error('未登录'); return }
  try {
    const task = await moviesApi.scrapeMovieSubtitles(token, id)
    ElMessage.success('已启动字幕爬取：' + (task.id ?? ''))
    dropdownRef.value?.handleClose()
  } catch { ElMessage.error('启动失败') }
}

const showCreate = ref(false)
function openCreateDialog() { showCreate.value = true }
const bulkFileInput = ref<HTMLInputElement | null>(null)
function openBulkImport() { bulkFileInput.value?.click() }
async function onBulkFileSelected(e: Event) {
  const input = e.target as HTMLInputElement | null
  const f = input?.files?.[0] ?? null
  if (input) input.value = ''
  const token = userStore.token ?? ''
  if (!token || !f) { ElMessage.error('未登录'); return }
  try {
    let uploadFile: File | Blob = f
    const name = f.name.toLowerCase()
    if (name.endsWith('.txt')) {
      const text = await f.text()
      const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean)
      const data = lines.map(t => ({ title: t }))
      uploadFile = new Blob([JSON.stringify(data)], { type: 'application/json' })
    }
    const task = await moviesApi.importMoviesBatch(token, uploadFile, { library_id: libraryId.value })
    ElMessage.success('已启动批量导入：' + (task.id ?? ''))
    showCreate.value = false
  } catch { ElMessage.error('批量导入失败') }
}

watch(pageSize, (size) => {
  movieStore.setSize(size)
})

watch(libraryId, async (newId, oldId) => {
  if (!newId || newId === oldId) return
  const token = userStore.token ?? ''
  if (!token) return
  libraryStore.setCurrentLibrary(newId)
  page.value = 1
  movieStore.setFilters({ library_id: newId, page: 1, size: pageSize.value })
  try {
    await movieStore.fetchList(token)
    await refreshPosters()
  } catch {}
}, { immediate: true })

const defaultsMovieForm = {
  title: '',
  title_cn: '',
  description: '',
  description_cn: '',
  release_date: '',
  directorsCsv: '',
  actorsCsv: '',
  genresCsv: '',
  tagsCsv: '',
  rating: null as number | null,
  duration: null as number | null,
  countryCsv: '',
  language: '',
}
const movieForm = ref({ ...defaultsMovieForm })
const canSubmit = computed(() => movieForm.value.title.trim().length > 0)


async function submitCreate() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  const payload: MovieCreateRequestSchema = {
    library_id: libraryId.value,
    title: movieForm.value.title.trim(),
    title_cn: movieForm.value.title_cn.trim(),
    directors: splitCsv(movieForm.value.directorsCsv),
    actors: splitCsv(movieForm.value.actorsCsv),
    description: movieForm.value.description.trim(),
    description_cn: movieForm.value.description_cn.trim(),
    release_date: movieForm.value.release_date ? movieForm.value.release_date : null,
    genres: splitCsv(movieForm.value.genresCsv),
    metadata: {
      duration: movieForm.value.duration ?? undefined,
      country: splitCsv(movieForm.value.countryCsv),
      language: movieForm.value.language || undefined,
    },
    rating: movieForm.value.rating ?? undefined,
    tags: splitCsv(movieForm.value.tagsCsv),
  }
  try {
    await movieStore.create(token, payload)
    ElMessage.success('电影已创建，任务已启动：' + (movieStore.lastCreateTaskId ?? ''))
    showCreate.value = false
    movieForm.value = { ...defaultsMovieForm }
  } catch {
    ElMessage.error('创建失败')
  }
}
</script>

<template>
  <!-- 三层结构：Header/Sider 由 App.vue 承载；此处仅实现内容区 -->
  <section class="library-detail content mode-media" :data-library-id="libraryId">
    <!-- 顶部：列表工具栏（单行图标化） -->
    <ListToolbar
      :total="total"
      :range-start="rangeStart"
      :range-end="rangeEnd"
      :view-mode="viewMode"
      :add-handler="openCreateDialog"
      @random="onRandom"
      @toggle-view="onToggleView"
      @open-sort="onOpenSort"
      @open-filter="onOpenFilter"
      @search="onSearch"
    />

    <!-- 内联过滤面板：轻量下拉（保持与网格合理间距） -->
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
      <p class="hint">提示：本页演示为库内媒体筛选；“只我/激活”在详情页不影响展示，仅保留 UI 一致性。</p>
    </div>

    <!-- 排序面板：字段 + 方向（与后端字段解耦） -->
    <div v-if="showSort" class="panel panel--sort">
      <SortSelect :sort-by="'date'" :sort-order="sortOrder" @update:sortBy="mapSortBy" @update:sortOrder="updateSortOrder" />
    </div>

    <!-- 中部：媒体网格（响应过滤/排序变化） -->
    <MediaGrid
      :items="paged"
      :dense="viewMode==='list'"
      :projector="(raw: any) => { const id=String(raw?.id ?? ''); const ent=movieStore.entities[id]; return { id, title: raw.title, poster: posterMap[id], rating: raw.rating, tags: raw.tags, isFavorite: ent?.is_favoriter===true, inWatchLater: ent?.is_watchLater===true } }"
      @open="onOpen"
      @play="(id) => console.log('play', id)"
      @preview="(id) => console.log('preview', id)"
      @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
      @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
      @contextmenu="onCardContextMenu"
    />

    <!-- 底部：分页导航（浅色主题降低透明度） -->
    <footer class="page-footer">
      <PaginationBar :page="page" :pageSize="pageSize" :total="total" @prev="prevPage" @next="nextPage" />
    </footer>

    <el-dialog v-model="showCreate" title="新增电影" width="560px" class="create-dialog">
      <div class="form">
        <div class="form-item">
          <div class="label">标题</div>
          <input class="input" v-model="movieForm.title" placeholder="电影标题" />
        </div>
        <div class="form-item">
          <div class="label">中文标题</div>
          <input class="input" v-model="movieForm.title_cn" placeholder="可选" />
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">导演</div>
            <input class="input" v-model="movieForm.directorsCsv" placeholder="逗号分隔" />
          </div>
          <div class="form-item">
            <div class="label">演员</div>
            <input class="input" v-model="movieForm.actorsCsv" placeholder="逗号分隔" />
          </div>
        </div>
        <div class="form-item">
          <div class="label">描述</div>
          <textarea class="textarea" v-model="movieForm.description" placeholder="简介" />
        </div>
        <div class="form-item">
          <div class="label">中文描述</div>
          <textarea class="textarea" v-model="movieForm.description_cn" placeholder="可选" />
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">上映日期</div>
            <input class="input" type="date" v-model="movieForm.release_date" />
          </div>
          <div class="form-item">
            <div class="label">评分</div>
            <input class="input" type="number" v-model.number="movieForm.rating" min="0" max="10" step="0.1" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">类型</div>
            <input class="input" v-model="movieForm.genresCsv" placeholder="逗号分隔" />
          </div>
          <div class="form-item">
            <div class="label">标签</div>
            <input class="input" v-model="movieForm.tagsCsv" placeholder="逗号分隔" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">国家/地区</div>
            <input class="input" v-model="movieForm.countryCsv" placeholder="逗号分隔" />
          </div>
          <div class="form-item">
            <div class="label">语言</div>
            <input class="input" v-model="movieForm.language" placeholder="可选" />
          </div>
        </div>
        <div class="form-item">
          <div class="label">时长（分钟）</div>
          <input class="input" type="number" v-model.number="movieForm.duration" min="1" />
        </div>
      </div>
      <template #footer>
        <div class="actions">
          <button class="btn btn--secondary" @click="openBulkImport">批量导入</button>
          <button class="btn btn--secondary" @click="showCreate=false">取消</button>
          <button class="btn btn--primary" :disabled="!canSubmit" @click="submitCreate">创建</button>
        </div>
      </template>
    </el-dialog>

    <el-dropdown
      ref="dropdownRef"
      :virtual-ref="virtualRef"
      virtual-triggering
      trigger="contextmenu"
      placement="bottom-start"
      :hide-on-click="true"
    >
  <template #dropdown>
    <el-dropdown-menu>
      <el-dropdown-item @click="changePoster"><el-icon><Picture /></el-icon> 更换封面</el-dropdown-item>
      <el-dropdown-item @click="openEdit"><el-icon><Edit /></el-icon> 编辑信息</el-dropdown-item>
      <el-dropdown-item @click="removeMovie" class="is-danger"><el-icon><Delete /></el-icon> 删除电影</el-dropdown-item>
      <el-dropdown-item @click="scrapeMetadata">爬取元数据</el-dropdown-item>
      <el-dropdown-item @click="scrapeSubtitles">爬取字幕</el-dropdown-item>
    </el-dropdown-menu>
  </template>
</el-dropdown>
<input ref="posterFileInput" type="file" accept="image/*" style="display:none" @change="onPosterFileSelected" />
<input ref="bulkFileInput" type="file" accept=".json,.txt" style="display:none" @change="onBulkFileSelected" />

    <el-dialog v-model="showEdit" title="编辑电影" width="560px" class="edit-dialog">
      <div class="form">
        <div class="form-item">
          <div class="label">标题</div>
          <input class="input" v-model="movieEditForm.title" placeholder="电影标题" />
        </div>
        <div class="form-item">
          <div class="label">中文标题</div>
          <input class="input" v-model="movieEditForm.title_cn" placeholder="可选" />
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">导演</div>
            <input class="input" v-model="movieEditForm.directorsCsv" placeholder="逗号分隔" />
          </div>
          <div class="form-item">
            <div class="label">演员</div>
            <input class="input" v-model="movieEditForm.actorsCsv" placeholder="逗号分隔" />
          </div>
        </div>
        <div class="form-item">
          <div class="label">描述</div>
          <textarea class="textarea" v-model="movieEditForm.description" placeholder="简介" />
        </div>
        <div class="form-item">
          <div class="label">中文描述</div>
          <textarea class="textarea" v-model="movieEditForm.description_cn" placeholder="可选" />
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">上映日期</div>
            <input class="input" type="date" v-model="movieEditForm.release_date" />
          </div>
          <div class="form-item">
            <div class="label">评分</div>
            <input class="input" type="number" v-model.number="movieEditForm.rating" min="0" max="10" step="0.1" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">类型</div>
            <input class="input" v-model="movieEditForm.genresCsv" placeholder="逗号分隔" />
          </div>
          <div class="form-item">
            <div class="label">标签</div>
            <input class="input" v-model="movieEditForm.tagsCsv" placeholder="逗号分隔" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">国家/地区</div>
            <input class="input" v-model="movieEditForm.countryCsv" placeholder="逗号分隔" />
          </div>
          <div class="form-item">
            <div class="label">语言</div>
            <input class="input" v-model="movieEditForm.language" placeholder="可选" />
          </div>
        </div>
        <div class="form-item">
          <div class="label">时长（分钟）</div>
          <input class="input" type="number" v-model.number="movieEditForm.duration" min="1" />
        </div>
      </div>
      <template #footer>
        <div class="actions">
          <button class="btn btn--secondary" @click="showEdit=false">取消</button>
          <button class="btn btn--primary" :disabled="!canSubmitEdit" @click="submitEdit">保存</button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.content { padding-block: var(--space-5); max-width: none; width: 100%; padding-inline: var(--content-pad); }
.library-detail { display: grid; gap: var(--space-4); }

/* 保持 Toolbar 与 Grid 的协调距离；暗黑影院风格 A 增强沉浸 */
.panel { border: 1px solid var(--border); background: color-mix(in oklab, var(--surface), var(--brand-weak) 4%); border-radius: var(--radius-lg); padding: var(--space-3); }
.panel--filter, .panel--sort { margin-top: -4px; }
.row { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
.cb { display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); }
.seg { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); }
.hint { margin-top: var(--space-2); color: var(--text-muted); font-size: var(--text-sm); }

/* 底部分页包裹：浅色主题降低透明度，深色略提升对比 */
.page-footer { display: flex; justify-content: center; }
:global(html[data-theme="light"]) .page-footer { opacity: 0.9; }
:global(html[data-theme="dark"]) .page-footer { opacity: 1; }

.form { display: grid; gap: var(--space-3); }
.form-row { display: grid; gap: var(--space-3); grid-template-columns: 1fr; }
@media (min-width: 720px) { .form-row { grid-template-columns: 1fr 1fr; } }
.form-item { display: grid; gap: 6px; }
.label { font-weight: 600; color: var(--text-secondary); }
.input, .textarea { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); color: var(--text); }
.input:hover, .textarea:hover { background: color-mix(in oklab, var(--surface), var(--brand-weak) 6%); }
.input:focus, .textarea:focus { outline: none; border-color: var(--brand); box-shadow: 0 0 0 2px color-mix(in oklab, var(--brand), transparent 80%); }
.actions { display: flex; justify-content: flex-end; gap: var(--space-3); }
.btn[disabled] { opacity: 0.6; cursor: not-allowed; }

/* Dropdown 主题适配 */
:global(.el-dropdown-menu) { background: var(--dropdown-bg); border: 1px solid var(--border); box-shadow: var(--shadow-2); }
:global(.el-dropdown-menu__item) { color: var(--text); }
:global(.el-dropdown-menu__item:hover) { background: color-mix(in oklab, var(--surface), var(--brand-weak) 8%); }
:global(.el-dropdown-menu__item.is-danger) { color: var(--danger); }
:global(.poster-dialog .poster-preview) { width: 240px; height: 150px; object-fit: cover; border-radius: var(--radius-lg); border: 1px solid var(--field-border); }
</style>
