<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import MediaGrid from '@/components/ui/MediaGrid.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import SortSelect from '@/components/ui/SortSelect.vue'
import LibraryCard from '@/components/ui/LibraryCard.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Picture, Edit, CircleClose, Delete } from '@element-plus/icons-vue'
import { useLibraryStore } from '@/stores/library'
import { useUserStore } from '@/stores/user'
import { libraries as librariesApi } from '@/api'
import { LibraryType, type LibraryCreateRequestSchema } from '@/types/library'

// 视图状态：搜索、视图模式、排序、过滤（与 LibraryDetail 保持一致的交互）
const searchQuery = ref('')
const viewMode = ref<'card' | 'list' | 'gallery'>('card')
type SortKey = 'updated_at' | 'created_at' | 'name' | 'media_count'
const sortBy = ref<SortKey>('updated_at')
const sortOrder = ref<'asc' | 'desc'>('desc')

const showOthersPublic = ref<boolean>(true)
const showInactive = ref<boolean>(false)
const showDeleted = ref<boolean>(false)

// 分页（与后端保持一致）
const page = ref(1)
const pageSize = ref(24)
const coverMap = ref<Record<string, string>>({})

// 右键菜单状态
const contextMenu = ref<{ visible: boolean; id: string | null; x: number; y: number }>({ visible: false, id: null, x: 0, y: 0 })
const virtualRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<any>(null)
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
function onCardContextMenu(payload: { id: string; x: number; y: number; target: HTMLElement | null }) {
  contextMenu.value = { visible: true, id: payload.id, x: payload.x, y: payload.y }
  const anchor = ensureVirtualRefAt(payload.x, payload.y)
  virtualRef.value = anchor
  dropdownRef.value?.handleOpen()
}

const contextIsActive = computed(() => {
  const id = contextMenu.value.id
  if (!id) return true
  const lib = libraryStore.list.find((i: any) => i.id === id)
  return lib?.is_active ?? true
})

// 编辑信息对话框
const showEdit = ref(false)
const editForm = ref<{ id: string | null; name: string; description: string; is_public: boolean; is_active: boolean }>({ id: null, name: '', description: '', is_public: true, is_active: true })
function openEdit() {
  const id = contextMenu.value.id
  if (!id) return
  const lib = libraryStore.list.find((i: any) => i.id === id) ?? null
  editForm.value = { id, name: lib?.name ?? '', description: lib?.description ?? '', is_public: lib?.is_public ?? true, is_active: lib?.is_active ?? true }
  showEdit.value = true
  contextMenu.value.visible = false
}
async function submitEdit() {
  const token = userStore.token ?? ''
  if (!token || !editForm.value.id) { ElMessage.error('未登录'); return }
  try {
    await libraryStore.update(token, editForm.value.id, { name: editForm.value.name, description: editForm.value.description, is_public: editForm.value.is_public, is_active: editForm.value.is_active })
    ElMessage.success('媒体库信息已更新')
    showEdit.value = false
  } catch { ElMessage.error('更新失败') }
}

// 更改封面
const coverFileInput = ref<HTMLInputElement | null>(null)
function changeCover() {
  const id = contextMenu.value.id
  if (!id) return
  coverFileInput.value?.click()
  contextMenu.value.visible = false
}
async function onChangeCoverFile(e: Event) {
  const input = e.target as HTMLInputElement | null
  const f = input?.files?.[0] ?? null
  input && (input.value = '')
  const token = userStore.token ?? ''
  const id = contextMenu.value.id
  if (!token || !id || !f) { return }
  try {
    await librariesApi.uploadLibraryCover(token, id, f)
    await refreshCovers()
    ElMessage.success('封面已更新')
  } catch { ElMessage.error('封面更新失败') }
}

// 停用/启用媒体库
async function toggleActive(active: boolean) {
  const id = contextMenu.value.id
  const token = userStore.token ?? ''
  if (!id || !token) { ElMessage.error('未登录'); return }
  try {
    await libraryStore.setActive(token, id, active)
    ElMessage.success(active ? '媒体库已启用' : '媒体库已停用')
  } catch { ElMessage.error('操作失败') }
  dropdownRef.value?.handleClose()
}

// 删除媒体库
async function removeLibrary() {
  const id = contextMenu.value.id
  const token = userStore.token ?? ''
  if (!id || !token) { ElMessage.error('未登录'); return }
  try {
    await ElMessageBox.confirm('删除后不可恢复，确认删除该媒体库？', '删除媒体库', { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' })
    await libraryStore.remove(token, id, true)
    ElMessage.success('媒体库已删除')
  } catch { /* 取消或失败 */ }
  dropdownRef.value?.handleClose()
}

// 列表数据源：来自 store
const libraryStore = useLibraryStore()
const userStore = useUserStore()

const libraryType = ref<LibraryType>(libraryStore.filters.library_type)

// 过滤与排序
const filtered = computed(() => {
  const base = libraryStore.list
  return base
})

const sorted = computed(() => {
  const base = [...filtered.value]
  const key = sortBy.value
  const dir = sortOrder.value === 'asc' ? 1 : -1
  base.sort((a: any, b: any) => {
    const av = a[key]
    const bv = b[key]
    const aVal = key === 'name' ? a.name : av
    const bVal = key === 'name' ? b.name : bv
    if (aVal == null && bVal == null) return 0
    if (aVal == null) return -1 * dir
    if (bVal == null) return 1 * dir
    const aTime = typeof aVal === 'string' && /\d{4}-\d{2}-\d{2}/.test(aVal) ? Date.parse(aVal) : (aVal as number | string)
    const bTime = typeof bVal === 'string' && /\d{4}-\d{2}-\d{2}/.test(bVal) ? Date.parse(bVal) : (bVal as number | string)
    if (aTime < bTime) return -1 * dir
    if (aTime > bTime) return 1 * dir
    return 0
  })
  return base
})

// 分页切片
const total = computed(() => libraryStore.listMeta.total)
const rangeStart = computed(() => (total.value ? (page.value - 1) * pageSize.value + 1 : 0))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
const paged = computed(() => sorted.value)

// 交互回调（透传自 ListToolbar 与 PaginationBar）
function onRandom() {
  const arr = sorted.value
  if (!arr.length) return
  const idx = Math.floor(Math.random() * arr.length)
  const pick = arr[idx]
  if (!pick) return
  onOpen(pick.id)
}

const router = useRouter()
function onOpen(id: string | number) {
  router.push(`/libraries/${id}`)
}
function onToggleView(mode: 'card' | 'list' | 'gallery') { viewMode.value = mode }
function onOpenSort() { showSort.value = !showSort.value }
function onOpenFilter() { showFilter.value = !showFilter.value }
async function onSearch(q: string) {
  searchQuery.value = q
  page.value = 1
  libraryStore.setFilters({ query: q, page: 1, page_size: pageSize.value })
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try {
    await libraryStore.fetchList(token)
    await refreshCovers()
  } catch { ElMessage.error('加载失败') }
}

// 过滤/排序面板开关
const showFilter = ref(false)
const showSort = ref(false)

// 将排序选择映射到本地 key（库列表：日期/标题/“评分”→ 媒体数量）
function mapSortBy(v: string) {
  switch (v) {
    case 'date': sortBy.value = 'updated_at'; break
    case 'title': sortBy.value = 'name'; break
    case 'rating': sortBy.value = 'media_count'; break
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
    libraryStore.setPage(page.value)
    const token = userStore.token ?? ''
    if (!token) { ElMessage.error('未登录'); return }
    try { await libraryStore.fetchList(token); await refreshCovers() } catch { ElMessage.error('加载失败') }
  }
}
async function nextPage() {
  const pageCount = Math.ceil(total.value / pageSize.value)
  if (page.value < pageCount) {
    page.value += 1
    libraryStore.setPage(page.value)
    const token = userStore.token ?? ''
    if (!token) { ElMessage.error('未登录'); return }
    try { await libraryStore.fetchList(token); await refreshCovers() } catch { ElMessage.error('加载失败') }
  }
}

// 将库条目映射为 LibraryCard 需要的 props
function projectLibrary(raw: unknown): Record<string, unknown> {
  const l = raw as any
  return {
    id: l.id,
    name: l.name,
    coverUrl: coverMap.value[l.id],
    library: l,
  }
}

const showCreate = ref(false)
const createForm = ref<{
  name: string
  type: LibraryType
  description: string
  scan_interval: number
  auto_import: boolean
  auto_import_scan_path: string | null
  auto_import_supported_formats: string[] | null
  is_public: boolean
  is_active: boolean
  metadata_plugins: string[]
  subtitle_plugins: string[]
  coverFile: File | null
}>({
  name: '',
  type: LibraryType.MOVIE,
  description: '',
  scan_interval: 60,
  auto_import: false,
  auto_import_scan_path: null,
  auto_import_supported_formats: null,
  is_public: true,
  is_active: true,
  metadata_plugins: [],
  subtitle_plugins: [],
  coverFile: null,
})

const metadataPluginOptions = ref([
  { label: 'TMDB', value: 'tmdb' },
  { label: 'IMDB', value: 'imdb' },
  { label: 'Local', value: 'local' },
])
const subtitlePluginOptions = ref([
  { label: 'OpenSubtitles', value: 'opensubtitles' },
  { label: 'ASSRT', value: 'assrt' },
  { label: 'Local', value: 'local' },
])

function openCreateDialog() { showCreate.value = true }

// 初始加载与筛选联动
watch(pageSize, (size) => {
  libraryStore.setPageSize(size)
})
watch(showOthersPublic, async (v) => {
  libraryStore.setFilters({ only_me: v ? undefined : true, page: 1 })
  page.value = 1
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await libraryStore.fetchList(token); await refreshCovers() } catch { ElMessage.error('加载失败') }
})
watch(showInactive, async (v) => {
  libraryStore.setFilters({ is_active: v ? undefined : true, page: 1 })
  page.value = 1
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await libraryStore.fetchList(token); await refreshCovers() } catch { ElMessage.error('加载失败') }
})
watch(showDeleted, async (v) => {
  libraryStore.setFilters({ is_deleted: v ? undefined : false, page: 1 })
  page.value = 1
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await libraryStore.fetchList(token); await refreshCovers() } catch { ElMessage.error('加载失败') }
})
watch(libraryType, async (v) => {
  libraryStore.setFilters({ library_type: v, page: 1 })
  page.value = 1
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await libraryStore.fetchList(token); await refreshCovers() } catch { ElMessage.error('加载失败') }
})

async function refreshCovers() {
  const token = userStore.token ?? ''
  if (!token) return
  const ids = libraryStore.list.map((l: any) => l.id)
  if (!ids.length) return
  try {
    const urls = await librariesApi.getLibraryCoversSigned(token, ids)
    const map: Record<string, string> = {}
    for (let i = 0; i < ids.length; i++) map[ids[i]] = urls[i]
    coverMap.value = { ...coverMap.value, ...map }
  } catch {}
}

onMounted(async () => {
  // 将本地分页与 store 对齐，并发起首次加载
  libraryStore.setPage(page.value)
  libraryStore.setPageSize(pageSize.value)
  const token = userStore.token ?? ''
  if (!token) return
  try { await libraryStore.fetchList(token); await refreshCovers() } catch { /* 静默 */ }
})

const coverPreviewUrl = ref<string | null>(null)
let coverObjectUrl: string | null = null
const canSubmit = computed(() => createForm.value.name.trim().length > 0)
watch(() => createForm.value.auto_import, (v) => {
  if (!v) {
    createForm.value.auto_import_scan_path = null
    createForm.value.auto_import_supported_formats = null
  }
})
const showType = ref(false)
const showMeta = ref(false)
const showSub = ref(false)
const typeLabel = computed(() => createForm.value.type === LibraryType.MOVIE ? '电影' : '剧集')
const metadataLabel = computed(() => {
  const map = new Map(metadataPluginOptions.value.map(i => [i.value, i.label]))
  const labels = (createForm.value.metadata_plugins ?? []).map(k => map.get(k)).filter(Boolean) as string[]
  return labels.length ? labels.join(', ') : '选择插件'
})
const subtitleLabel = computed(() => {
  const map = new Map(subtitlePluginOptions.value.map(i => [i.value, i.label]))
  const labels = (createForm.value.subtitle_plugins ?? []).map(k => map.get(k)).filter(Boolean) as string[]
  return labels.length ? labels.join(', ') : '选择插件'
})
function toggleType() { showType.value = !showType.value }
function closeType() { showType.value = false }
function selectType(v: LibraryType) { createForm.value.type = v; showType.value = false }
function toggleMeta() { showMeta.value = !showMeta.value }
function closeMeta() { showMeta.value = false }
function onMetaFocusOut(e: FocusEvent) {
  const el = e.currentTarget as HTMLElement
  const next = e.relatedTarget as Node | null
  if (!next || !el.contains(next)) showMeta.value = false
}
function toggleMetadata(v: string) {
  const arr = createForm.value.metadata_plugins
  const idx = arr.indexOf(v)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(v)
}
function toggleSub() { showSub.value = !showSub.value }
function closeSub() { showSub.value = false }
function onSubFocusOut(e: FocusEvent) {
  const el = e.currentTarget as HTMLElement
  const next = e.relatedTarget as Node | null
  if (!next || !el.contains(next)) showSub.value = false
}
function toggleSubtitle(v: string) {
  const arr = createForm.value.subtitle_plugins
  const idx = arr.indexOf(v)
  if (idx >= 0) arr.splice(idx, 1)
  else arr.push(v)
}

async function submitCreate() {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  const payload: LibraryCreateRequestSchema = {
    name: createForm.value.name,
    type: createForm.value.type,
    description: createForm.value.description,
    scan_interval: createForm.value.scan_interval,
    auto_import: createForm.value.auto_import,
    auto_import_scan_path: createForm.value.auto_import_scan_path ?? undefined,
    auto_import_supported_formats: createForm.value.auto_import_supported_formats ?? undefined,
    is_public: createForm.value.is_public,
    is_active: createForm.value.is_active,
    metadata_plugins: createForm.value.metadata_plugins,
    subtitle_plugins: createForm.value.subtitle_plugins,
  }
  try {
    const lib = await libraryStore.create(token, payload)
    if (createForm.value.coverFile) {
      await librariesApi.uploadLibraryCover(token, lib.id, createForm.value.coverFile)
    }
    ElMessage.success('媒体库已创建')
    showCreate.value = false
    createForm.value = {
      name: '',
      type: LibraryType.MOVIE,
      description: '',
      scan_interval: 60,
      auto_import: false,
      auto_import_scan_path: null,
      auto_import_supported_formats: null,
      is_public: true,
      is_active: true,
      metadata_plugins: [],
      subtitle_plugins: [],
      coverFile: null,
    }
    if (coverObjectUrl) { URL.revokeObjectURL(coverObjectUrl); coverObjectUrl = null }
    coverPreviewUrl.value = null
  } catch {
    ElMessage.error('创建失败')
  }
}

function onFormatsChange(e: Event) {
  const input = e.target as HTMLInputElement | null
  const v = input?.value ?? ''
  createForm.value.auto_import_supported_formats = v
    ? v.split(',').map((s) => s.trim()).filter((s) => s.length > 0)
    : null
}

function onCoverChange(e: Event) {
  const input = e.target as HTMLInputElement | null
  const f = input?.files?.[0] ?? null
  createForm.value.coverFile = f
  if (coverObjectUrl) { URL.revokeObjectURL(coverObjectUrl) }
  coverObjectUrl = f ? URL.createObjectURL(f) : null
  coverPreviewUrl.value = coverObjectUrl
}
</script>

<template>
  <!-- 三层结构：Header/Sider 由 App.vue 承载；此处仅实现内容区 -->
  <section class="library-list content mode-media">
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
        <label class="cb"><input type="checkbox" v-model="showOthersPublic"> 显示他人公共库</label>
        <label class="cb"><input type="checkbox" v-model="showInactive"> 显示已停用</label>
        <label class="cb"><input type="checkbox" v-model="showDeleted"> 显示已删除</label>
      </div>
      <div class="row">
        <label class="cb"><input type="radio" :value="LibraryType.MOVIE" v-model="libraryType"> 电影</label>
        <label class="cb"><input type="radio" :value="LibraryType.TV" v-model="libraryType"> 剧集</label>
      </div>
      <p class="hint">提示：此页展示媒体库列表；可按类型、他人公共库、停用与删除状态筛选。</p>
    </div>

    <!-- 排序面板：字段 + 方向（与后端字段解耦） -->
    <div v-if="showSort" class="panel panel--sort">
      <SortSelect :sort-by="'date'" :sort-order="sortOrder" @update:sortBy="mapSortBy" @update:sortOrder="updateSortOrder" />
    </div>

    <!-- 中部：库卡片网格（响应过滤/排序变化） -->
    <MediaGrid
      :items="paged"
      :dense="viewMode==='list'"
      :item-component="LibraryCard"
      :projector="projectLibrary"
      @open="onOpen"
      @contextmenu="onCardContextMenu"
    />

    <!-- 底部：分页导航（浅色主题降低透明度） -->
    <footer class="page-footer">
      <PaginationBar :page="page" :pageSize="pageSize" :total="total" @prev="prevPage" @next="nextPage" />
    </footer>

    <el-dialog v-model="showCreate" title="新建媒体库" width="560px" class="create-dialog">
      <div class="form">
        <div class="form-item">
          <div class="label">名称</div>
          <input class="input" v-model="createForm.name" placeholder="媒体库名称" />
        </div>
        <div class="form-item">
          <div class="label">类型</div>
          <div class="select-field" tabindex="0" @click="toggleType" @blur="closeType">
            <span class="value">{{ typeLabel }}</span>
            <span class="arrow" :class="{ open: showType }">▾</span>
            <div v-if="showType" class="dropdown">
              <div class="option" :class="{ active: createForm.type===LibraryType.MOVIE }" @mousedown.prevent="selectType(LibraryType.MOVIE)">电影</div>
              <div class="option" :class="{ active: createForm.type===LibraryType.TV }" @mousedown.prevent="selectType(LibraryType.TV)">剧集</div>
            </div>
          </div>
        </div>
        <div class="form-item">
          <div class="label">描述</div>
          <textarea class="textarea" v-model="createForm.description" placeholder="描述" />
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">扫描间隔</div>
            <input class="input" type="number" v-model.number="createForm.scan_interval" min="1" />
            <small class="help">单位为分钟</small>
          </div>
          <div class="form-item">
            <div class="label">自动导入</div>
            <label class="cb"><input type="checkbox" v-model="createForm.auto_import" /> 启用</label>
            <small class="help">启用后将按路径与格式规则自动加入</small>
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">自动导入路径</div>
            <input class="input" v-model="createForm.auto_import_scan_path" placeholder="可选" :disabled="!createForm.auto_import" />
            <small class="help">示例：/Volumes/Media/Movies</small>
          </div>
          <div class="form-item">
            <div class="label">支持格式</div>
            <input class="input" :value="createForm.auto_import_supported_formats?.join(', ') ?? ''" placeholder="逗号分隔" @change="onFormatsChange" :disabled="!createForm.auto_import" />
            <small class="help">例：mp4, mkv, avi</small>
          </div>
        </div>
        <div class="form-row">
          <div class="form-item">
            <div class="label">METADATA获取</div>
            <div class="select-field" tabindex="0" @click="toggleMeta" @focusout="onMetaFocusOut">
              <span class="value"><template v-if="createForm.metadata_plugins.length"><span v-for="opt in metadataPluginOptions.filter(o => createForm.metadata_plugins.includes(o.value))" :key="opt.value" class="chip">{{ opt.label }}</span></template><template v-else>选择插件</template></span>
              <span class="arrow" :class="{ open: showMeta }">▾</span>
              <div v-if="showMeta" class="dropdown">
                <label v-for="opt in metadataPluginOptions" :key="opt.value" class="option checkbox" @mousedown.prevent="toggleMetadata(opt.value)">
                  <input type="checkbox" :checked="createForm.metadata_plugins.includes(opt.value)" @change="toggleMetadata(opt.value)" />
                  <span class="text">{{ opt.label }}</span>
                </label>
              </div>
            </div>
          </div>
          <div class="form-item">
            <div class="label">SUBTITLE获取</div>
            <div class="select-field" tabindex="0" @click="toggleSub" @focusout="onSubFocusOut">
              <span class="value"><template v-if="createForm.subtitle_plugins.length"><span v-for="opt in subtitlePluginOptions.filter(o => createForm.subtitle_plugins.includes(o.value))" :key="opt.value" class="chip">{{ opt.label }}</span></template><template v-else>选择插件</template></span>
              <span class="arrow" :class="{ open: showSub }">▾</span>
              <div v-if="showSub" class="dropdown">
                <label v-for="opt in subtitlePluginOptions" :key="opt.value" class="option checkbox" @mousedown.prevent="toggleSubtitle(opt.value)">
                  <input type="checkbox" :checked="createForm.subtitle_plugins.includes(opt.value)" @change="toggleSubtitle(opt.value)" />
                  <span class="text">{{ opt.label }}</span>
                </label>
              </div>
            </div>
          </div>
        </div>
        <div class="form-item">
          <div class="label">封面</div>
          <div class="cover-upload">
            <input type="file" accept="image/*" @change="onCoverChange" />
            <img v-if="coverPreviewUrl" :src="coverPreviewUrl" class="cover-preview" />
          </div>
        </div>
        <div class="form-row">
          <label class="cb"><input type="checkbox" v-model="createForm.is_public" /> 公开</label>
          <label class="cb"><input type="checkbox" v-model="createForm.is_active" /> 激活</label>
        </div>
      </div>
      <template #footer>
        <div class="actions">
          <button class="btn btn--secondary" @click="showCreate=false">取消</button>
          <button class="btn btn--primary" :disabled="!canSubmit" @click="submitCreate">创建</button>
        </div>
      </template>
    </el-dialog>

    <!-- 右键菜单（Element Plus Dropdown，虚拟触发定位到鼠标处） -->
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
          <el-dropdown-item @click="changeCover"><el-icon><Picture /></el-icon> 更改封面</el-dropdown-item>
          <el-dropdown-item @click="openEdit"><el-icon><Edit /></el-icon> 编辑信息</el-dropdown-item>
          <el-dropdown-item @click="toggleActive(!contextIsActive)"><el-icon><CircleClose /></el-icon> {{ contextIsActive ? '停用媒体库' : '启用媒体库' }}</el-dropdown-item>
          <el-dropdown-item @click="removeLibrary" class="is-danger"><el-icon><Delete /></el-icon> 删除媒体库</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 隐藏文件选择器：用于更改封面 -->
    <input ref="coverFileInput" type="file" accept="image/*" class="hidden-file" @change="onChangeCoverFile" />

    <!-- 编辑信息对话框 -->
    <el-dialog v-model="showEdit" title="编辑媒体库" width="480px" class="edit-dialog">
      <div class="form">
        <div class="form-item">
          <div class="label">名称</div>
          <input class="input" v-model="editForm.name" placeholder="媒体库名称" />
        </div>
        <div class="form-item">
          <div class="label">描述</div>
          <textarea class="textarea" v-model="editForm.description" placeholder="描述" />
        </div>
        <div class="form-row">
          <label class="cb"><input type="checkbox" v-model="editForm.is_public" /> 公开</label>
          <label class="cb"><input type="checkbox" v-model="editForm.is_active" /> 激活</label>
        </div>
      </div>
      <template #footer>
        <div class="actions">
          <button class="btn btn--secondary" @click="showEdit=false">取消</button>
          <button class="btn btn--primary" @click="submitEdit">保存</button>
        </div>
      </template>
    </el-dialog>
  </section>
 </template>

<style scoped>
.content { padding-block: var(--space-5); max-width: none; width: 100%; padding-inline: var(--content-pad); }
.library-list { display: grid; gap: var(--space-4); }

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
.help { font-size: var(--text-sm); color: var(--text-muted); }

.input, .textarea { width: 100%; padding: 10px 12px; border: 1px solid var(--field-border); border-radius: var(--radius-lg); background: var(--field-bg); color: var(--text); transition: background 120ms, border-color 120ms, box-shadow 120ms; }
.input:hover, .textarea:hover { background: var(--field-hover); }
.input:focus, .textarea:focus { outline: none; border-color: var(--field-focus); box-shadow: var(--field-focus-shadow); }

.select-field { position: relative; display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid var(--field-border); border-radius: var(--radius-lg); background: var(--field-bg); color: var(--text); cursor: pointer; transition: background 120ms, border-color 120ms, box-shadow 120ms; }
.select-field:hover { background: var(--field-hover); }
.select-field:focus { outline: none; border-color: var(--field-focus); box-shadow: var(--field-focus-shadow); }
.select-field .arrow { line-height: 1; color: var(--text-secondary); transition: transform 120ms; }
.select-field .arrow.open { transform: rotate(180deg); }
.select-field .dropdown { position: absolute; left: 0; right: 0; top: calc(100% + 6px); z-index: 20; background: var(--dropdown-bg); border: 1px solid var(--field-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-md); padding: 8px; display: grid; gap: 4px; color: var(--dropdown-text); }
.select-field .option { padding: 8px 10px; border-radius: var(--radius-md); color: var(--dropdown-text); }
.select-field .option:hover { background: var(--dropdown-hover); }
.select-field .option.active { background: var(--dropdown-active); }
.select-field .value { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; min-height: 20px; }
.select-field .chip { display: inline-flex; align-items: center; padding: 2px 6px; border-radius: var(--radius-md); background: var(--field-chip-bg); border: 1px solid var(--field-border); font-size: var(--text-sm); }
.select-field .option.checkbox { display: grid; grid-template-columns: 18px 1fr; align-items: center; gap: 8px; }
.select-field .option.checkbox input { accent-color: var(--brand); }

.cover-upload { display: inline-flex; align-items: center; gap: var(--space-3); }
.cover-preview { width: 96px; height: 60px; object-fit: cover; border-radius: var(--radius-lg); border: 1px solid var(--field-border); }

.actions { display: flex; justify-content: flex-end; gap: var(--space-3); }
.btn[disabled] { opacity: 0.6; cursor: not-allowed; }

.library-list { --field-bg: color-mix(in oklab, var(--surface), var(--brand-weak) 4%); --field-hover: color-mix(in oklab, var(--surface), var(--brand-weak) 8%); --field-border: var(--border); --field-focus: var(--brand); --field-focus-shadow: 0 0 0 3px color-mix(in oklab, var(--brand), transparent 80%); --field-chip-bg: color-mix(in oklab, var(--surface), var(--brand-weak) 6%); --dropdown-bg: #ffffff; --dropdown-hover: #f2f3f5; --dropdown-active: #e6e8eb; --dropdown-text: var(--text); }
:global(html[data-theme="light"]) .library-list { --field-bg: color-mix(in oklab, var(--surface), white 6%); --field-hover: color-mix(in oklab, var(--surface), white 10%); --field-border: color-mix(in oklab, var(--border), var(--brand-weak) 8%); --field-focus: var(--brand); --field-focus-shadow: 0 0 0 3px color-mix(in oklab, var(--brand), transparent 78%); --field-chip-bg: color-mix(in oklab, var(--surface), white 8%); --dropdown-bg: #ffffff; --dropdown-hover: #f2f3f5; --dropdown-active: #e6e8eb; --dropdown-text: var(--text); }
:global(html[data-theme="dark"]) .library-list { --field-bg: color-mix(in oklab, var(--surface), black 12%); --field-hover: color-mix(in oklab, var(--surface), black 16%); --field-border: color-mix(in oklab, var(--border), var(--brand-weak) 12%); --field-focus: var(--brand); --field-focus-shadow: 0 0 0 3px color-mix(in oklab, var(--brand), transparent 70%); --field-chip-bg: color-mix(in oklab, var(--surface), black 10%); --dropdown-bg: #1e1e22; --dropdown-hover: #26262b; --dropdown-active: #2e2e34; --dropdown-text: var(--text); }

/* 右键菜单样式（浅/深色通过变量适配） */
.hidden-file { position: fixed; left: -10000px; top: -10000px; width: 1px; height: 1px; opacity: 0; }

/* Dropdown 主题适配 */
:global(.el-dropdown-menu) { background: var(--dropdown-bg); border: 1px solid var(--field-border); box-shadow: var(--shadow-2); }
:global(.el-dropdown-menu__item) { color: var(--dropdown-text); }
:global(.el-dropdown-menu__item:hover) { background: var(--dropdown-hover); }
:global(.el-dropdown-menu__item.is-danger) { color: var(--danger); }
.hidden-file { position: fixed; left: -10000px; top: -10000px; width: 1px; height: 1px; opacity: 0; }
</style>
