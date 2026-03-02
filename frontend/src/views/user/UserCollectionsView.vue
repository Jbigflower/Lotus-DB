<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import MediaCard from '@/components/ui/MediaCard.vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useUserCollectionsStore } from '@/stores/user_collections'
import { useMovieStore } from '@/stores/movie'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import { CustomListType } from '@/types/user_collection'
import { useUsersStore } from '@/stores/users'
import { movies as moviesApi } from '@/api'

defineOptions({ name: 'UserCollectionsPage' })

type MovieItem = {
  id: string | number
  title: string
  poster?: string
  year?: number
  rating?: number
  genres?: string[]
  tags?: string[]
}

type Collection = {
  id: string
  title: string
  description?: string
  isPublic: boolean
  count: number
  movies: MovieItem[]
}

// 滚动容器引用
const scrollEl = ref<HTMLElement | null>(null)
const router = useRouter()
const route = useRoute()

const userStore = useUserStore()
const collStore = useUserCollectionsStore()
const movieStore = useMovieStore()
const usersStore = useUsersStore()
const isLoading = ref(false)
const loadedUntil = ref(0)
const coversByCollection = ref<Record<string, Record<string, string>>>({})

// 工具栏与筛选/排序/搜索状态
const searchQuery = ref('')
const onlyMine = ref(false)
const sortKey = ref<'created_at' | 'updated_at'>('created_at')
const sortOrder = ref<'asc' | 'desc'>('desc')
const showFilter = ref(false)
const showSort = ref(false)

// 新建弹窗
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref<{ name: string; description?: string; is_public: boolean }>({ name: '', description: '', is_public: true })
const createRules = {
  name: [
    { required: true, message: '片单名称为必填项', trigger: 'blur' },
    { min: 1, max: 64, message: '长度需在 1-64 字符', trigger: 'blur' },
  ],
  description: [
    { max: 500, message: '描述不超过 500 字', trigger: 'blur' },
  ],
}

// 简易模拟后端请求
function delay<T>(data: T, ms = 350) {
  return new Promise<T>(resolve => setTimeout(() => resolve(data), ms))
}

function makeFakeMovie(seed: number): MovieItem {
  const id = `m-${seed}`
  const genrePool: string[] = ['剧情', '科幻', '动作']
  const genre: string = genrePool[seed % genrePool.length]
  return {
    id,
    title: `电影 #${seed}`,
    poster: `https://picsum.photos/seed/uc${seed}/1280/720`,
    year: 2010 + (seed % 14),
    rating: +(6 + (seed % 40) / 10).toFixed(1),
    genres: [genre],
    tags: seed % 2 ? ['热门'] : ['冷门'],
  }
}

function makeFakeCollection(idx: number): Collection {
  const movieCount = 6 + (idx % 20)
  const sampleMovies = Array.from({ length: Math.min(movieCount, 20) }, (_, i) => makeFakeMovie(idx * 21 + i))
  const titles = ['收藏夹 Favorite', '待观看 Watchlist', '自建片单 A', '自建片单 B', '导演精选', '年度必看']
  const title = titles[idx % titles.length]
  return {
    id: `c-${idx}`,
    title,
    description: `这是关于「${title}」的简短描述，展示该片单的主题与目的。`,
    isPublic: idx % 3 !== 0,
    count: movieCount,
    movies: sampleMovies,
  }
}

async function ensureMovies(upto: number) {
  if (isLoading.value) return
  isLoading.value = true
  const token = userStore.token ?? ''
  if (!token) { isLoading.value = false; ElMessage.error('未登录'); return }
  const list = collStore.list
  const end = Math.min(upto, list.length)
  for (let i = loadedUntil.value; i < end; i += 1) {
    const id = list[i]?.id
    if (id) {
      try {
        await collStore.fetchMovies(token, id)
        const items = collStore.moviesById[id] ?? []
        const ids = items.filter((m: any) => m?.has_poster === true).map((m: any) => m.id)
        const existing = coversByCollection.value[id] ?? {}
        const uncachedIds = ids.filter((mid: string) => !existing[mid])
        if (uncachedIds.length > 0) {
          let urls: string[] = []
          try { urls = await moviesApi.getMovieCoversSigned(token, uncachedIds, 'poster.jpg') } catch {}
          const map: Record<string, string> = { ...existing }
          for (let k = 0; k < uncachedIds.length; k += 1) {
            const u = urls[k]
            if (u) map[uncachedIds[k]] = u
          }
          coversByCollection.value[id] = map
        } else if (!coversByCollection.value[id]) {
          coversByCollection.value[id] = existing
        }
      } catch { }
    }
  }
  loadedUntil.value = end
  isLoading.value = false
}

// 虚拟滚动（固定高度估算）
const SECTION_EST_HEIGHT = 420 // 估算：标题+属性栏+操作+一行卡片
const buffer = 3
const startIdx = ref(0)

const containerHeight = ref(0)
const total = computed(() => collStore.list.length)
const windowSize = computed(() => Math.ceil(containerHeight.value / SECTION_EST_HEIGHT) + buffer)

// 由 startIdx + windowSize 推导出 endIdx，避免在 computed 内产生副作用
const endIdx = computed(() => {
  const start = startIdx.value
  const size = windowSize.value
  return Math.min(total.value, Math.max(start + size, start + 1))
})

// 搜索
const searchedList = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return collStore.list
  return collStore.list.filter((c) => {
    const name = String(c.name ?? '').toLowerCase()
    const desc = String(c.description ?? '').toLowerCase()
    return name.includes(q) || desc.includes(q)
  })
})

// 仅我的片单过滤
const filteredList = computed(() => {
  if (!onlyMine.value) return searchedList.value
  const uid = userStore.user?.id
  if (!uid) return []
  return searchedList.value.filter((c) => c.user_id === uid)
})

// 排序
const sortedList = computed(() => {
  const key = sortKey.value
  const order = sortOrder.value
  const list = [...filteredList.value]
  list.sort((a, b) => {
    const av = a[key] ?? ''
    const bv = b[key] ?? ''
    const at = av ? Date.parse(String(av)) : 0
    const bt = bv ? Date.parse(String(bv)) : 0
    const cmp = at - bt
    return order === 'asc' ? cmp : -cmp
  })
  return list
})

const visibleCollections = computed(() => {
  const start = startIdx.value
  const end = endIdx.value
  return sortedList.value.slice(start, end)
})

const padTop = computed(() => startIdx.value * SECTION_EST_HEIGHT)
const padBottom = computed(() => Math.max(0, (total.value - endIdx.value) * SECTION_EST_HEIGHT))

let ticking = false
function onScroll() {
  if (!scrollEl.value) return
  const el = scrollEl.value
  if (!ticking) {
    window.requestAnimationFrame(() => {
      containerHeight.value = el.clientHeight
      const nextStart = Math.max(0, Math.floor(el.scrollTop / SECTION_EST_HEIGHT) - buffer)
      startIdx.value = Math.min(nextStart, Math.max(0, total.value - 1))

      // 触底懒加载（无限加载）
      const nearBottom = el.scrollTop + el.clientHeight > el.scrollHeight - SECTION_EST_HEIGHT
      if (nearBottom) ensureMovies(startIdx.value + windowSize.value + 16)

      ticking = false
    })
    ticking = true
  }
}

onMounted(async () => {
  const token = userStore.token ?? ''
  if (!token) { ElMessage.error('未登录'); return }
  try { await collStore.fetchList(token) } catch { }
  // 拉取公开片单所属用户的名称与头像签名
  try {
    const ids = Array.from(new Set(collStore.list.filter((c:any) => c.is_public).map((c:any) => c.user_id).filter(Boolean)))
    if (ids.length > 0) {
      const [nameMap, avatars] = await Promise.all([
        usersStore.getMapping(token, ids),
        usersStore.getProfilesSigned(token, ids),
      ])
      for (let i = 0; i < ids.length; i += 1) {
        const id = ids[i]
        ownerNameById.value[id] = nameMap[id] ?? id
        ownerAvatarById.value[id] = avatars[i] ?? ''
      }
    }
  } catch {}
  await ensureMovies(18)
  containerHeight.value = scrollEl.value?.clientHeight ?? 0
  // 初始计算与滚动绑定
  startIdx.value = 0
  scrollEl.value?.addEventListener('scroll', onScroll, { passive: true })
  if (String(route.query.create || '') === '1') { showCreate.value = true }
})

onUnmounted(() => {
  scrollEl.value?.removeEventListener('scroll', onScroll)
})

function onEdit(collection: any) {
  // TODO: 打开编辑弹窗或路由到编辑页
  console.log('edit collection', collection.id)
}

function onDelete(collection: any) {
  // TODO: 确认后删除该片单
  console.log('delete collection', collection.id)
}

function gotoCollection(id: string) {
  router.push({ name: 'list-detail', params: { id } })
}

function openCreateDialog() { showCreate.value = true }
function resetCreate() {
  createForm.value = { name: '', description: '', is_public: true }
}
async function submitCreate(formEl: any) {
  if (!formEl) return
  await formEl.validate(async (valid: boolean) => {
    if (!valid) return
    const token = userStore.token ?? ''
    if (!token) { ElMessage.error('未登录'); return }
    creating.value = true
    try {
      await collStore.create(token, {
        name: createForm.value.name,
        description: createForm.value.description ?? '',
        is_public: createForm.value.is_public,
        movies: [],
        type: CustomListType.CUSTOMLIST,
      })
      await collStore.fetchList(token)
      ElMessage.success('已创建片单')
      showCreate.value = false
      resetCreate()
    } catch (e: any) {
      ElMessage.error(String(e?.message ?? e))
    } finally {
      creating.value = false
    }
  })
}
function onSearch(q: string) { searchQuery.value = q }
function openFilterPanel() { showFilter.value = true }
function openSortPanel() { showSort.value = true }

// 所属用户信息映射
const ownerNameById = ref<Record<string, string>>({})
const ownerAvatarById = ref<Record<string, string>>({})
</script>

<template>
  <div ref="scrollEl" class="collections-page">
    <ListToolbar
      :total="filteredList.length"
      view-mode="list"
      :disable-view-toggle="true"
      :add-handler="openCreateDialog"
      @search="onSearch"
      @open-filter="openFilterPanel"
      @open-sort="openSortPanel"
    />

    <!-- 筛选面板：仅我的片单 -->
    <el-drawer v-model="showFilter" title="筛选" size="320px">
      <div class="drawer-body">
        <el-checkbox v-model="onlyMine">仅展示我的片单</el-checkbox>
      </div>
      <template #footer>
        <el-button @click="showFilter=false">关闭</el-button>
      </template>
    </el-drawer>

    <!-- 排序面板：创建/更新时间 + 升降序 -->
    <el-drawer v-model="showSort" title="排序" size="320px">
      <div class="drawer-body">
        <el-form label-position="top" class="el-reset">
          <el-form-item label="排序字段">
            <el-select v-model="sortKey" style="width:100%">
              <el-option label="创建时间" value="created_at" />
              <el-option label="更新时间" value="updated_at" />
            </el-select>
          </el-form-item>
          <el-form-item label="顺序">
            <el-select v-model="sortOrder" style="width:100%">
              <el-option label="降序" value="desc" />
              <el-option label="升序" value="asc" />
            </el-select>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <el-button type="primary" @click="showSort=false">确定</el-button>
      </template>
    </el-drawer>

    <!-- 新增片单弹窗 -->
    <el-dialog v-model="showCreate" title="新增片单" width="560px" class="create-dialog">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-position="top" class="el-reset" @submit.prevent>
        <el-form-item label="片单名称" prop="name">
          <el-input v-model="createForm.name" placeholder="必填" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="片单描述" prop="description">
          <el-input v-model="createForm.description" type="textarea" placeholder="可选" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="公开可见">
          <el-switch v-model="createForm.is_public" active-text="公开" inactive-text="私密" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate=false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate($refs.createFormRef)">提交</el-button>
      </template>
    </el-dialog>
    <div class="virtual-pad" :style="{ paddingTop: padTop + 'px', paddingBottom: padBottom + 'px' }">
      <section
        v-for="c in visibleCollections"
        :key="c.id"
        class="collection-section"
        role="button"
        tabindex="0"
        @click="gotoCollection(c.id)"
        @keydown.enter="gotoCollection(c.id)"
      >
        <div class="collection-header">
          <h2 class="collection-title" @click.stop="gotoCollection(c.id)">{{ c.name }}</h2>
          <div class="collection-actions">
            <button class="icon-btn" title="编辑该片单" aria-label="编辑" @click.stop="onEdit(c)">✏️</button>
            <button class="icon-btn danger" title="删除该片单" aria-label="删除" @click.stop="onDelete(c)">🗑️</button>
          </div>
        </div>
        <div class="collection-meta">
          <span class="meta-item">{{ (collStore.moviesById[c.id]?.length ?? c.movies.length) }} 部影片</span>
          <span class="meta-dot">•</span>
          <span class="meta-item" :class="c.is_public ? 'tag-public' : 'tag-private'">{{ c.is_public ? 'Public' : 'Private' }}</span>
          <template v-if="c.is_public">
            <span class="meta-dot">•</span>
            <span class="meta-owner">
              <img
                v-if="ownerAvatarById[c.user_id]"
                :src="ownerAvatarById[c.user_id]"
                :alt="ownerNameById[c.user_id] ?? 'Owner'"
                class="avatar"
                referrerpolicy="no-referrer"
                loading="lazy"
              />
              <span class="owner-name">{{ ownerNameById[c.user_id] ?? c.user_id }}</span>
            </span>
          </template>
          <span class="meta-dot">•</span>
          <span class="meta-desc">{{ c.description }}</span>
        </div>

        <div class="card-row media-row">
          <div v-for="m in (collStore.moviesById[c.id] ?? [])" :key="m.id" class="card-item">
            <MediaCard
              :id="m.id"
              :title="m.title"
              :poster="coversByCollection[c.id]?.[m.id]"
              :year="m.year"
              :rating="m.rating"
              :genres="m.genres"
              :tags="m.tags"
              :is-favorite="m.is_favoriter === true"
              :in-watch-later="m.is_watchLater === true"
              @toggle-favorite="(id) => movieStore.toggleFavorite(id)"
              @toggle-watch-later="(id) => movieStore.toggleWatchLater(id)"
            />
          </div>
        </div>
      </section>
      <div v-if="isLoading || collStore.loading" class="loading">正在加载片单…</div>
      <div v-else-if="!hasMore" class="loading done">已无更多片单</div>
    </div>
  </div>
</template>

<style scoped>
.collections-page {
  height: 100%;
  overflow: auto;
  padding: clamp(16px, 4vw, 32px);
  display: grid;
  gap: clamp(20px, 3.2vw, 32px);
  background: var(--bg);
}

.drawer-body { display: grid; gap: 16px; }

.virtual-pad { display: grid; gap: clamp(16px, 2.6vw, 24px); }

.collection-section {
  display: grid;
  gap: 10px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-1);
  padding: clamp(12px, 2.4vw, 18px);
  animation: fadeSlideIn 280ms ease both;
  cursor: pointer;
}

.collection-header { display: flex; align-items: baseline; justify-content: space-between; }
.collection-title {
  margin: 0;
  font-size: clamp(var(--text-xl), 3.2vw, 1.9rem);
  color: var(--text-primary);
  letter-spacing: 0.3px;
}
.collection-actions { display: flex; gap: 8px; }
.icon-btn {
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-secondary);
  border-radius: var(--radius-pill);
  padding: 6px 10px;
  font-size: var(--text-sm);
  transition: transform 160ms ease, filter 160ms ease, background 160ms ease, color 160ms ease;
}
.icon-btn:hover { background: color-mix(in oklab, var(--surface), var(--brand-weak) 12%); color: var(--text-primary); transform: translateY(-1px); }
.icon-btn.danger { color: var(--danger); }

.collection-meta { display: flex; align-items: center; gap: 8px; color: var(--text-secondary); }
.meta-item { font-size: var(--text-sm); }
.meta-desc { font-size: var(--text-sm); color: var(--text-muted); }
.meta-dot { opacity: 0.5; }
.tag-public { color: var(--success); }
.tag-private { color: var(--danger); }

.meta-owner { display: inline-flex; align-items: center; gap: 6px; }
.meta-owner .avatar {
  width: 20px; height: 20px; border-radius: 50%; object-fit: cover;
  border: 1px solid color-mix(in oklab, var(--surface-3), transparent 50%);
}
.meta-owner .owner-name { font-size: var(--text-sm); opacity: 0.95; }

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
.card-item { scroll-snap-align: start; transition: transform 160ms ease, filter 160ms ease; overflow: visible; }
.card-item:hover { transform: translateY(-2px) scale(1.02); filter: brightness(1.08); }
.media-row { grid-auto-columns: clamp(240px, 22vw, 320px); }

.loading { 
  color: var(--text-secondary);
  padding: 10px 0;
  text-align: center;
}
.loading.done { opacity: 0.8; }

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 统一使用设计系统变量完成明暗适配 */
</style>
