<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useSystemStore } from '@/stores/system'
import { useResourceStore } from '@/stores/resource'
import { useOpsLogStore } from '@/stores/ops_log'
import { system } from '@/api'

const userStore = useUserStore()
const sys = useSystemStore()
const res = useResourceStore()
const ops = useOpsLogStore()

const pollingTimer = ref<number | null>(null)

async function manualRefresh() {
  try {
    if (userStore.token) {
      await sys.refresh()
      await sys.fetchActivities(userStore.token)
      ElMessage.success('已刷新服务器信息')
    }
  } catch (e) {
    ElMessage.error(sys.error ?? '刷新失败')
    console.error(e)
  }
}

async function startPolling() {
  await manualRefresh()
  if (pollingTimer.value) clearInterval(pollingTimer.value)
  pollingTimer.value = window.setInterval(() => {
    sys.refresh().catch(() => {})
    if (userStore.token) {
      sys.fetchActivities(userStore.token).catch(() => {})
    }
  }, 30000)
}

onMounted(() => {
  startPolling()
  res.startPolling(userStore.token ?? undefined, 10000)
})

onBeforeUnmount(() => {
  if (pollingTimer.value) clearInterval(pollingTimer.value)
  res.stopPolling()
})

async function confirmAndDo(action: 'restart' | 'shutdown') {
  if (!userStore.token) return ElMessage.error('未登录')
  const title = action === 'restart' ? '确认重启服务器？' : '确认关闭服务器？'
  const msg = action === 'restart' ? '重启可能导致服务短暂不可用' : '关闭将停止所有服务'
  try {
    await ElMessageBox.confirm(msg, title, { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
    const fn = action === 'restart' ? system.restart : system.shutdown
    const resu = await fn(userStore.token)
    if (resu.ok) {
      ElMessage.success(action === 'restart' ? '已发送重启指令' : '已发送关闭指令')
      ops.add({ user: userStore.user?.username ?? null, action, target: 'server', result: 'success' })
    } else {
      ElMessage.error(resu.message ?? '操作失败')
      ops.add({ user: userStore.user?.username ?? null, action, target: 'server', result: 'error', message: resu.message })
    }
  } catch {
    ops.add({ user: userStore.user?.username ?? null, action, target: 'server', result: 'cancel' })
  }
}

function percentText(v?: number | null, scale = 1) {
  const n = (v ?? 0) * scale
  return `${Math.round(n)}%`
}

function formatSize(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDateTime(iso?: string | null) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString();
}

const diskUsageList = computed(() => {
  const map = res.usage?.disk ?? {};
  return Object.entries(map).map(([key, val]) => ({
    name: key,
    ...val
  }));
});
</script>

<template>
  <div class="admin-dashboard">
    <!-- 服务器信息模块 -->
    <section class="card mb-6">
      <header class="card__header">
        <div class="header-left">
          <h3>服务器信息</h3>
          <el-tag type="info" effect="plain" class="ml-2">v{{ sys.version?.app_version ?? '-' }}</el-tag>
        </div>
        <div class="actions">
          <button class="btn" @click="manualRefresh">刷新</button>
          <button class="btn btn-primary" @click="confirmAndDo('restart')">重启</button>
          <button class="btn btn-danger" @click="confirmAndDo('shutdown')">关闭</button>
        </div>
      </header>
      <div class="card__body">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="应用名称">{{ sys.version?.app_name ?? '未知' }}</el-descriptions-item>
          <el-descriptions-item label="运行环境">{{ sys.version?.environment ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="健康状态">
            <el-tag :type="sys.health?.overall === 'ok' ? 'success' : 'danger'">
              {{ sys.health?.overall?.toUpperCase() ?? 'UNKNOWN' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-for="i in sys.appStatusList" :key="i.key" :label="i.key">
            {{ i.value }}
          </el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="sys.error" :title="sys.error" type="error" show-icon class="mt-4" />
      </div>
    </section>

    <!-- 资源监控模块 -->
    <section class="card mb-6">
      <header class="card__header"><h3>资源监控</h3></header>
      <div class="card__body">
        <div class="monitors-container">
          <!-- CPU & Memory -->
          <div class="resource-rings">
            <div class="monitor">
              <div class="ring" :class="{ danger: res.cpuDanger }">
                <span>{{ percentText(res.cpuPercent, 1) }}</span>
              </div>
              <label>CPU使用率</label>
            </div>
            <div class="monitor">
              <div class="ring" :class="{ danger: res.memDanger }">
                <span>{{ percentText(res.memPercent, 1) }}</span>
              </div>
              <label>内存占用</label>
            </div>
          </div>
          
          <!-- Disk Usage -->
          <div class="disk-usage">
            <h4>存储占用概览</h4>
            <div class="disk-grid">
              <div v-for="item in diskUsageList" :key="item.name" class="disk-card">
                <div class="disk-name">{{ item.name }}</div>
                <div class="disk-value">{{ formatSize(item.size_bytes) }}</div>
                <div class="disk-meta">{{ item.file_count }} 文件 / {{ item.dir_count }} 目录</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 用户活动追踪模块 -->
    <section class="card">
      <header class="card__header"><h3>用户活动追踪</h3></header>
      <div class="card__body">
        <el-table :data="sys.activities" style="width: 100%" stripe>
          <el-table-column prop="username" label="用户名" width="120" fixed />
          <el-table-column prop="device" label="设备" min-width="180" />
          <el-table-column prop="ip" label="IP地址" width="140" />
          <el-table-column prop="location" label="位置" width="120">
            <template #default="{ row }">
              {{ row.location || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="login_at" label="登录时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.login_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="last_active_at" label="最后活跃" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.last_active_at) }}
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.admin-dashboard { padding: var(--space-6); max-width: 1200px; margin: 0 auto; }
.mb-6 { margin-bottom: 24px; }
.ml-2 { margin-left: 8px; }
.mt-4 { margin-top: 16px; }

.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); }
.card__header { display:flex; align-items:center; justify-content: space-between; padding: var(--space-4); border-bottom: 1px solid var(--border); }
.header-left { display: flex; align-items: center; }
.card__body { padding: var(--space-4); }

.actions { display:flex; gap: var(--space-2); }
.btn { padding: 8px 12px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); cursor: pointer; transition: all 0.2s; }
.btn:hover { background: var(--surface-hover); }
.btn-primary { background: var(--brand); color: var(--on-brand, #fff); border-color: var(--brand); }
.btn-primary:hover { background: var(--brand-hover); }
.btn-danger { background: #c0392b; color: #fff; border-color: #c0392b; }
.btn-danger:hover { background: #e74c3c; }

.monitors-container { display: flex; gap: 48px; align-items: flex-start; flex-wrap: wrap; }
.resource-rings { display:flex; gap: 32px; }
.monitor { display:flex; flex-direction: column; align-items: center; gap: 8px; }
.ring { width: 100px; height: 100px; border-radius: 50%; display:grid; place-items:center; border: 8px solid color-mix(in oklab, var(--brand-weak), var(--surface) 50%); font-size: 1.2em; font-weight: bold; }
.ring.danger { border-color: #e74c3c; color: #e74c3c; }

.disk-usage { flex: 1; min-width: 300px; }
.disk-usage h4 { margin: 0 0 16px 0; font-size: 14px; color: var(--text-secondary); }
.disk-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
.disk-card { background: var(--surface-hover); padding: 12px; border-radius: var(--radius); border: 1px solid var(--border-light); }
.disk-name { font-weight: 500; margin-bottom: 4px; color: var(--text-primary); }
.disk-value { font-size: 1.2em; font-weight: bold; color: var(--brand); margin-bottom: 4px; }
.disk-meta { font-size: 12px; color: var(--text-secondary); }
</style>
