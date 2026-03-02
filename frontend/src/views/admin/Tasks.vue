<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import MetadataViewerDialog from '@/components/ui/MetadataViewerDialog.vue'
import { useUserStore } from '@/stores/user'
import { useTasksStore } from '@/stores/tasks'
import { TaskStatus, TaskType } from '@/types/task'
import type { TaskRead } from '@/types/task'

const userStore = useUserStore()
const tasks = useTasksStore()

const quick = ref('')
const showFilterDialog = ref(false)
const showSortDialog = ref(false)
const showDetailDialog = ref(false)
const currentDetail = ref<TaskRead | null>(null)

// 筛选表单
const filterForm = ref<{ status: TaskStatus | null; task_type: TaskType | null }>({
  status: null,
  task_type: null,
})

// 排序表单
const sortBy = ref<'created_at' | 'updated_at' | 'priority' | 'status' | 'progress' | null>('created_at')
const sortOrder = ref<'asc' | 'desc'>('desc')

onMounted(() => {
  tasks.fetchList(userStore.token ?? '', { page: 1, size: 20 }).catch(() => {})
  tasks.startAutoRefresh(userStore.token ?? '', 3000)
})

onUnmounted(() => {
  tasks.stopAutoRefresh()
})

function onSearch(q: string) {
  quick.value = q
  tasks.fetchList(userStore.token ?? '', { query: q, page: 1 }).catch(() => {})
}

function openFilterDialog() {
  filterForm.value.status = tasks.filters.status ?? null
  filterForm.value.task_type = tasks.filters.task_type ?? null
  showFilterDialog.value = true
}

function applyFilter() {
  tasks.setFilters({
    status: filterForm.value.status ?? undefined,
    task_type: filterForm.value.task_type ?? undefined,
  })
  tasks.fetchList(userStore.token ?? '', { page: 1 }).catch(() => {})
  showFilterDialog.value = false
}

function clearFilter() {
  filterForm.value = { status: null, task_type: null }
}

function openSortDialog() {
  sortBy.value = tasks.sortKey
  sortOrder.value = tasks.sortOrder
  showSortDialog.value = true
}

function applySort() {
  if (sortBy.value) {
    tasks.setSort(sortBy.value, sortOrder.value)
  }
  showSortDialog.value = false
}

// 列表数据（使用 Store 中的排序列表）
const tableData = computed(() => tasks.sortedList)

// 操作处理
async function openDetail(taskId: string) {
  try {
    const task = await tasks.fetchById(userStore.token ?? '', taskId)
    currentDetail.value = task
    showDetailDialog.value = true
  } catch {
    ElMessage.error('获取详情失败')
  }
}

async function handleCancel(row: TaskRead) {
  try {
    await ElMessageBox.confirm(`确认取消任务 "${row.name}"？`, '取消任务', { type: 'warning' })
    await tasks.cancel(userStore.token ?? '', row.id)
    ElMessage.success('任务已取消')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('取消失败')
  }
}

async function handleRetry(row: TaskRead) {
  try {
    await tasks.retry(userStore.token ?? '', row.id)
    ElMessage.success('任务重试请求已发送')
  } catch {
    ElMessage.error('重试失败')
  }
}

async function handleDelete(row: TaskRead) {
  try {
    await ElMessageBox.confirm(`删除后不可恢复，确认删除任务 "${row.name}"？`, '删除任务', { type: 'warning' })
    await tasks.remove(userStore.token ?? '', row.id)
    ElMessage.success('任务已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

// 状态标签颜色映射
function getStatusType(status: TaskStatus) {
  switch (status) {
    case TaskStatus.COMPLETED: return 'success'
    case TaskStatus.FAILED: return 'danger'
    case TaskStatus.RUNNING: return 'primary'
    case TaskStatus.RETRYING: return 'warning'
    case TaskStatus.CANCELLED: return 'info'
    case TaskStatus.PAUSED: return 'warning'
    default: return 'info'
  }
}
</script>

<template>
  <div class="admin-tasks">
    <ListToolbar
      :viewMode="'list'"
      :disableViewToggle="true"
      :hideAdd="true"
      @search="onSearch"
      @open-filter="openFilterDialog"
      @open-sort="openSortDialog"
    />

    <section class="card section">
      <div class="table-wrap">
        <el-table :data="tableData" size="small" style="width: 100%" v-loading="tasks.loading">
          <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
          
          <el-table-column prop="description" label="描述" min-width="200">
             <template #default="{ row }">
               <el-tooltip :content="row.description || '无描述'" placement="top" :disabled="!row.description">
                 <span class="truncate-text">{{ row.description || '-' }}</span>
               </el-tooltip>
             </template>
          </el-table-column>

          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="进度" width="150">
            <template #default="{ row }">
              <el-progress 
                :percentage="Math.round((tasks.progressPercentById[row.id] || 0) * 100)" 
                :status="row.status === 'failed' ? 'exception' : undefined"
                :stroke-width="6"
              />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="260" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openDetail(row.id)">详情</el-button>
              
              <el-button 
                v-if="['pending', 'running', 'retrying', 'paused'].includes(row.status)"
                size="small" 
                type="warning" 
                @click="handleCancel(row)"
              >取消</el-button>
              
              <el-button 
                v-if="['failed', 'cancelled'].includes(row.status)"
                size="small" 
                type="primary" 
                @click="handleRetry(row)"
              >重试</el-button>
              
              <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <PaginationBar 
        :page="tasks.listMeta.page" 
        :pageSize="tasks.listMeta.size" 
        :total="tasks.listMeta.total" 
        @change="(p: number) => tasks.fetchList(userStore.token ?? '', { page: p })" 
      />
    </section>

    <!-- Filter Dialog -->
    <el-dialog v-model="showFilterDialog" title="筛选任务" width="400px">
      <el-form label-width="80px">
        <el-form-item label="状态">
          <el-select v-model="filterForm.status" placeholder="全部" style="width: 100%" clearable>
            <el-option v-for="s in Object.values(TaskStatus)" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filterForm.task_type" placeholder="全部" style="width: 100%" clearable>
            <el-option v-for="t in Object.values(TaskType)" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="clearFilter">清空</el-button>
        <el-button type="primary" @click="applyFilter">应用</el-button>
      </template>
    </el-dialog>

    <!-- Sort Dialog -->
    <el-dialog v-model="showSortDialog" title="排序" width="400px">
      <el-form label-width="80px">
        <el-form-item label="排序字段">
          <el-select v-model="sortBy" placeholder="选择字段" style="width: 100%">
            <el-option label="创建时间" value="created_at" />
            <el-option label="更新时间" value="updated_at" />
            <el-option label="优先级" value="priority" />
            <el-option label="状态" value="status" />
            <el-option label="进度" value="progress" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="sortOrder" style="width: 100%">
            <el-option label="升序" value="asc" />
            <el-option label="降序" value="desc" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSortDialog = false">取消</el-button>
        <el-button type="primary" @click="applySort">应用</el-button>
      </template>
    </el-dialog>

    <!-- Metadata Viewer -->
    <MetadataViewerDialog 
      v-model="showDetailDialog" 
      :data="currentDetail || {}" 
      title="任务详情元数据" 
    />
  </div>
</template>

<style scoped>
.admin-tasks { padding: var(--space-6); display: grid; gap: var(--space-5); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.table-wrap { overflow: auto; border-radius: var(--radius-md); }

.truncate-text {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

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
</style>
