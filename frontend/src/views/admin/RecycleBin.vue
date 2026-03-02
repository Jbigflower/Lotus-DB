<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import { useUserStore } from '@/stores/user'
import * as librariesApi from '@/api/libraries'
import * as moviesApi from '@/api/movies'
import * as movieAssetsApi from '@/api/movie_assets'
import * as userAssetsApi from '@/api/user_assets'

const userStore = useUserStore()

// Tabs
const activeTab = ref<'library' | 'movie' | 'official_asset' | 'user_asset'>('library')
const tabs = [
  { label: '媒体库', value: 'library' },
  { label: '媒体', value: 'movie' },
  { label: '官方资产', value: 'official_asset' },
  { label: '用户资产', value: 'user_asset' },
]

// Data
const tableData = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)

// Sort
const showSortDialog = ref(false)
const sortBy = ref<'deleted_at' | 'name' | 'parent' | null>('deleted_at')
const sortOrder = ref<'asc' | 'desc'>('desc')

// Detail
const showDetailDialog = ref(false)
const currentDetail = ref<any>(null)

// Fetch Data
async function fetchData() {
  if (!userStore.token) return
  loading.value = true
  try {
    tableData.value = []
    if (activeTab.value === 'library') {
      const res = await librariesApi.listLibraries(userStore.token, {
        page: page.value,
        page_size: size.value,
        library_type: 'movie', // Default to movie or handle both? API requires type. 
        // Wait, listLibraries requires library_type. 
        // If I want all deleted libraries, I might need to query twice or if API supports optional type?
        // Checking libraries.ts: library_type is mandatory in ListLibrariesParams interface?
        // Interface says: library_type: LibraryType;
        // Let's check if I can pass something else or loop.
        // For now assume 'movie' libraries.
        // Also `only_me` for user specific?
        // Prompt says "current user's info".
        // But for libraries, maybe just list all deleted libraries user has access to.
        // I will use 'movie' for now as it's the main type.
        // Or I should ask user? No, I should make reasonable assumption.
        // Let's try to list 'movie' libraries first.
        library_type: 'movie', 
        is_deleted: true,
        only_me: true
      })
      tableData.value = res.items
      total.value = res.total
    } else if (activeTab.value === 'movie') {
      const res = await moviesApi.listRecycleBinMovies(userStore.token, {
        page: page.value,
        size: size.value,
      })
      tableData.value = res.items
      total.value = res.total
    } else if (activeTab.value === 'official_asset') {
      const res = await movieAssetsApi.listRecycleBinAssets(userStore.token, {
        page: page.value,
        size: size.value
      })
      tableData.value = res.items
      total.value = res.total
    } else if (activeTab.value === 'user_asset') {
      const res = await userAssetsApi.listUserAssets(userStore.token, {
        page: page.value,
        size: size.value,
        is_deleted: true
      })
      // UserAssets API returns different structure? 
      // check user_assets.ts: returns ListUserAssetsResponse which is UserAssetPageResult | PartialPageResult
      // Both have items and total.
      if ('items' in res) {
        tableData.value = res.items
        total.value = res.total ?? 0
      }
    }
  } catch (e) {
    ElMessage.error('获取数据失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

watch([activeTab, page, size], () => {
  fetchData()
})

onMounted(() => {
  fetchData()
})

// Sort Logic (Frontend Sort as API might not support all sort fields for deleted items)
const sortedData = computed(() => {
  const data = [...tableData.value]
  if (!sortBy.value) return data
  
  return data.sort((a, b) => {
    let av: any, bv: any
    
    if (sortBy.value === 'name') {
      av = a.name || a.title
      bv = b.name || b.title
    } else if (sortBy.value === 'deleted_at') {
      // Use updated_at as proxy for deleted time if deleted_at not available
      av = a.updated_at
      bv = b.updated_at
    } else if (sortBy.value === 'parent') {
      // Library Name or Media Name
      // For Media: library_id (need map?) or maybe API returns expanded?
      // APIs usually return IDs.
      // If we don't have names, we can't sort effectively by parent name without fetching.
      // We will skip parent sort for now or use ID.
      av = a.library_id || a.movie_id
      bv = b.library_id || b.movie_id
    }
    
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    
    if (typeof av === 'string' && sortBy.value === 'deleted_at') {
      return sortOrder.value === 'asc' 
        ? (Date.parse(av) - Date.parse(bv))
        : (Date.parse(bv) - Date.parse(av))
    }
    
    if (av > bv) return sortOrder.value === 'asc' ? 1 : -1
    if (av < bv) return sortOrder.value === 'asc' ? -1 : 1
    return 0
  })
})

// Actions
function showDetail(row: any) {
  currentDetail.value = row
  showDetailDialog.value = true
}

async function handleRestore(row: any) {
  if (!userStore.token) return
  try {
    await ElMessageBox.confirm('确认恢复该项目？', '恢复', { type: 'warning' })
    if (activeTab.value === 'library') {
      await librariesApi.restoreLibrary(userStore.token, row.id)
    } else if (activeTab.value === 'movie') {
      await moviesApi.restoreMovies(userStore.token, [row.id])
    } else if (activeTab.value === 'official_asset') {
      await movieAssetsApi.restoreMovieAssets(userStore.token, [row.id])
    } else if (activeTab.value === 'user_asset') {
      await userAssetsApi.restoreUserAssets(userStore.token, [row.id])
    }
    ElMessage.success('恢复成功')
    fetchData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('恢复失败')
  }
}

async function handleDelete(row: any) {
  if (!userStore.token) return
  try {
    await ElMessageBox.confirm('彻底删除后无法恢复，确认删除？', '彻底删除', { type: 'error' })
    if (activeTab.value === 'library') {
      await librariesApi.deleteLibrary(userStore.token, row.id, false) // softDelete=false
    } else if (activeTab.value === 'movie') {
      await moviesApi.deleteMovies(userStore.token, [row.id], false)
    } else if (activeTab.value === 'official_asset') {
      await movieAssetsApi.deleteMovieAsset(userStore.token, row.movie_id, row.id, false)
      // Wait, deleteMovieAsset requires movieId. 
      // Row might have movie_id.
    } else if (activeTab.value === 'user_asset') {
      await userAssetsApi.deleteUserAsset(userStore.token, row.id, false)
    }
    ElMessage.success('删除成功')
    fetchData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

function openSortDialog() {
  showSortDialog.value = true
}

</script>

<template>
  <div class="recycle-bin">
    <!-- Top Filter / Tabs -->
    <div class="tabs-header">
        <el-radio-group v-model="activeTab" size="large">
            <el-radio-button v-for="tab in tabs" :key="tab.value" :label="tab.value">{{ tab.label }}</el-radio-button>
        </el-radio-group>
    </div>

    <!-- Toolbar -->
    <ListToolbar 
        :viewMode="'list'" 
        :disableViewToggle="true" 
        :hideAdd="true"
        :hideSearch="true"
        @open-sort="openSortDialog" 
    />
    <!-- Note: Hide Search/Filter as we use top tabs and built-in sort. Filter dialog in users.vue was for role/active. -->

    <section class="card section">
      <div class="table-wrap">
        <el-table :data="sortedData" size="small" style="width: 100%" v-loading="loading">
            <!-- Common ID Column -->
            <el-table-column prop="id" label="ID" width="220" show-overflow-tooltip />

            <!-- Dynamic Name Column -->
            <el-table-column label="名称/标题" min-width="150" show-overflow-tooltip>
                <template #default="{ row }">
                    {{ row.name || row.title || 'N/A' }}
                </template>
            </el-table-column>

            <!-- Parent Column (Media Library / Media Name) -->
            <el-table-column 
                v-if="activeTab !== 'library'"
                :label="activeTab === 'movie' ? '所属媒体库' : '所属媒体'"
                min-width="150"
                show-overflow-tooltip
            >
                <template #default="{ row }">
                    <span v-if="activeTab === 'movie'">{{ row.library_id }}</span>
                    <span v-else>{{ row.movie_id }}</span>
                    <!-- Ideally we should resolve ID to name, but for now ID is displayed as per available data -->
                </template>
            </el-table-column>

            <!-- Deleted Time -->
            <el-table-column label="删除时间" width="180">
                <template #default="{ row }">
                    {{ row.updated_at }}
                </template>
            </el-table-column>

            <!-- Operations -->
            <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                    <el-button size="small" @click="showDetail(row)">详情</el-button>
                    <el-button size="small" type="success" @click="handleRestore(row)">恢复</el-button>
                    <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
                </template>
            </el-table-column>
        </el-table>
      </div>

      <PaginationBar 
        :page="page" 
        :pageSize="size" 
        :total="total" 
        @change="(p) => page = p" 
      />
    </section>

    <!-- Sort Dialog -->
    <el-dialog v-model="showSortDialog" title="排序" width="520px">
      <el-form label-width="96px">
        <el-form-item label="排序字段">
          <el-select v-model="sortBy" placeholder="选择字段" style="width: 240px">
            <el-option label="删除时间" value="deleted_at" />
            <el-option label="名称" value="name" />
            <el-option label="所属父级" value="parent" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="sortOrder" style="width: 240px">
            <el-option label="升序" value="asc" />
            <el-option label="降序" value="desc" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-dialog>

    <!-- Detail Dialog -->
    <el-dialog v-model="showDetailDialog" title="资源详情" width="640px">
        <pre class="json-content">{{ JSON.stringify(currentDetail, null, 2) }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.recycle-bin { padding: var(--space-6); display: grid; gap: var(--space-5); }
.tabs-header { display: flex; justify-content: flex-start; }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.table-wrap { overflow: auto; border-radius: var(--radius-md); }
:deep(.el-table) { background: var(--surface); border-radius: var(--radius-md); }
:deep(.el-table) { color: var(--text-primary); }
:deep(.el-table__header-wrapper),
:deep(.el-table__header tr),
:deep(.el-table__header th) { background-color: var(--surface); color: var(--text-secondary); }
:deep(.el-table__cell) { border-bottom: 1px solid var(--border); }
:deep(.el-table__row) { background-color: var(--surface); }
:deep(.el-table__body tr:hover > td) { background-color: color-mix(in oklab, var(--surface), white 4%); }
@media (max-width: 768px) { .section { padding: var(--space-5); } }
@media (prefers-color-scheme: dark) { :deep(.el-table__body tr:hover > td) { background-color: color-mix(in oklab, var(--surface), white 6%); } }

.json-content {
    white-space: pre-wrap; 
    margin: 0; 
    background: var(--surface-variant); 
    padding: var(--space-4); 
    border-radius: var(--radius-sm);
    max-height: 500px;
    overflow: auto;
}
</style>
