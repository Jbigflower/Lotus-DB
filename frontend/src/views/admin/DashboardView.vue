<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import { useLibraryStore } from '@/stores/library'
import { useMovieStore } from '@/stores/movie'
import { useUserAssetsStore } from '@/stores/user_assets'
import { useTasksStore } from '@/stores/tasks'
import { useUserStore } from '@/stores/user'
import { getGlobalAssets } from '@/api/movie_assets'
import type { AssetRead } from '@/types/asset'
import type { LibraryRead } from '@/types/library'
import type { MovieRead } from '@/types/movie'
import type { UserAssetRead } from '@/types/user_asset'
import type { TaskRead } from '@/types/task'

const userStore = useUserStore()
const libraryStore = useLibraryStore()
const movieStore = useMovieStore()
const userAssetStore = useUserAssetsStore()
const taskStore = useTasksStore()

const activeTab = ref<'libraries' | 'movies' | 'official_assets' | 'user_assets' | 'tasks'>('libraries')
const loading = ref(false)
const tableData = ref<(LibraryRead | MovieRead | AssetRead | UserAssetRead | TaskRead)[]>([])
const pagination = ref({ page: 1, size: 20, total: 0 })

// Official Assets Local State
const officialAssets = ref<AssetRead[]>([])

// Helper to format bytes
function formatSize(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// Helper to format date
function formatDate(dateStr: string) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString()
}

// Data Fetching
async function fetchData() {
  if (!userStore.token) return
  loading.value = true
  try {
    const { page, size } = pagination.value
    
    switch (activeTab.value) {
      case 'libraries':
        await libraryStore.fetchList(userStore.token, { page, page_size: size })
        tableData.value = libraryStore.list
        pagination.value = { ...libraryStore.listMeta }
        break
        
      case 'movies':
        await movieStore.fetchList(userStore.token, { page, size })
        tableData.value = movieStore.list
        pagination.value = { ...movieStore.listMeta }
        break
        
      case 'official_assets':
        const res = await getGlobalAssets(userStore.token, { page, size })
        officialAssets.value = res.items
        tableData.value = res.items
        pagination.value = { page: res.page, size: res.size, total: res.total }
        break
        
      case 'user_assets':
        await userAssetStore.fetchList(userStore.token, { page, size })
        tableData.value = userAssetStore.list
        pagination.value = { ...userAssetStore.listMeta }
        break
        
      case 'tasks':
        await taskStore.fetchList(userStore.token, { page, size })
        tableData.value = taskStore.list
        pagination.value = { ...taskStore.listMeta }
        break
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

// Watchers
watch(activeTab, () => {
  pagination.value.page = 1
  fetchData()
})

onMounted(() => {
  fetchData()
})

function onPageChange(page: number) {
  pagination.value.page = page
  fetchData()
}
</script>

<template>
  <div class="admin-dashboard">
    <!-- Top Toolbar with Tabs -->
    <div class="toolbar">
      <el-radio-group v-model="activeTab" size="large">
        <el-radio-button label="libraries">媒体库</el-radio-button>
        <el-radio-button label="movies">媒体</el-radio-button>
        <el-radio-button label="official_assets">官方资产</el-radio-button>
        <el-radio-button label="user_assets">用户资产</el-radio-button>
        <el-radio-button label="tasks">后台任务</el-radio-button>
      </el-radio-group>
      <div class="actions">
        <el-button @click="fetchData" :loading="loading" circle icon="Refresh" />
      </div>
    </div>

    <!-- Main Content Area -->
    <section class="card section">
      <div class="table-wrap">
        
        <!-- Libraries Table -->
        <el-table v-if="activeTab === 'libraries'" :data="tableData" size="small" style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="220" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="root_path" label="路径" />
          <el-table-column label="最后扫描" width="180">
            <template #default="{ row }">{{ formatDate(row.last_scan) }}</template>
          </el-table-column>
        </el-table>

        <!-- Movies Table -->
        <el-table v-if="activeTab === 'movies'" :data="tableData" size="small" style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="220" />
          <el-table-column prop="title" label="标题" />
          <el-table-column prop="year" label="年份" width="80" />
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>

        <!-- Official Assets Table -->
        <el-table v-if="activeTab === 'official_assets'" :data="tableData" size="small" style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="220" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="movie_id" label="关联电影ID" width="220" />
          <el-table-column prop="path" label="路径" />
          <el-table-column label="大小" width="100">
            <template #default="{ row }">{{ formatSize(row.metadata?.size || 0) }}</template>
          </el-table-column>
        </el-table>

        <!-- User Assets Table -->
        <el-table v-if="activeTab === 'user_assets'" :data="tableData" size="small" style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="220" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="user_id" label="用户ID" width="220" />
          <el-table-column label="上传时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>

        <!-- Tasks Table -->
        <el-table v-if="activeTab === 'tasks'" :data="tableData" size="small" style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="220" />
          <el-table-column prop="type" label="类型" width="150" />
          <el-table-column prop="status" label="状态" width="100">
             <template #default="{ row }">
               <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">{{ row.status }}</el-tag>
             </template>
          </el-table-column>
          <el-table-column label="进度" width="200">
            <template #default="{ row }">
              <el-progress :percentage="row.progress?.percent || 0" :status="row.status === 'failed' ? 'exception' : undefined" />
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
        </el-table>

      </div>

      <PaginationBar 
        :page="pagination.page" 
        :pageSize="pagination.size" 
        :total="pagination.total" 
        @change="onPageChange" 
      />
    </section>
  </div>
</template>

<style scoped>
.admin-dashboard { padding: var(--space-6); display: grid; gap: var(--space-5); }
.toolbar { display: flex; justify-content: space-between; align-items: center; background: var(--surface); padding: var(--space-4) var(--space-6); border-radius: var(--radius-lg); box-shadow: var(--shadow-1); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); background: var(--surface); }
.table-wrap { overflow: auto; border-radius: var(--radius-md); }
:deep(.el-table) { background: var(--surface); border-radius: var(--radius-md); color: var(--text-primary); }
:deep(.el-table__header-wrapper),
:deep(.el-table__header tr),
:deep(.el-table__header th) { background-color: var(--surface); color: var(--text-secondary); }
:deep(.el-table__cell) { border-bottom: 1px solid var(--border); }
:deep(.el-table__row) { background-color: var(--surface); }
:deep(.el-table__body tr:hover > td) { background-color: color-mix(in oklab, var(--surface), white 4%); }
@media (max-width: 768px) { .section { padding: var(--space-5); } .toolbar { flex-direction: column; gap: var(--space-4); } }
@media (prefers-color-scheme: dark) { :deep(.el-table__body tr:hover > td) { background-color: color-mix(in oklab, var(--surface), white 6%); } }
</style>