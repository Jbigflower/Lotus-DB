<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { UserRole } from '@/types/user'
import { ElMessageBox, ElMessage } from 'element-plus'
import { auth } from '@/api'
import type { DeviceSessionRead } from '@/types/user'

const router = useRouter()
const store = useUserStore()

const username = computed(() => store.user?.username ?? '未登录')
const isAdmin = computed(() => store.user?.role === UserRole.ADMIN)

type DeviceItem = { id: string; agent: string; time: string; ip: string; location?: string; is_current?: boolean; ua?: string; platform?: string; alias?: string }
const devices = ref<DeviceItem[]>([])
const loadingDevices = ref(false)

async function refreshDevices() {
  if (!store.token) {
    ElMessage.error('请先登录')
    return
  }
  loadingDevices.value = true
  try {
    const list = await auth.listDevices(store.token)
    devices.value = list.map((d: DeviceSessionRead) => ({
      id: d.session_id,
      agent: `${(d.alias ?? d.user_agent ?? '未知')} · ${(d.platform ?? '')}`.trim(),
      time: new Date(d.created_at).toLocaleString(),
      ip: d.ip ?? '-',
      is_current: d.is_current,
      location: d.location ?? undefined,
      ua: d.user_agent ?? undefined,
      platform: d.platform ?? undefined,
      alias: d.alias ?? undefined,
    })) as unknown as DeviceItem[]
    ElMessage.success('已刷新登录记录')
  } catch (e) {
    ElMessage.error('刷新登录记录失败')
  } finally {
    loadingDevices.value = false
  }
}

async function logoutDevice(id: string) {
  if (!store.token) {
    ElMessage.error('请先登录')
    return
  }
  const target = devices.value.find(d => d.id === id)
  if (!target) return
  try {
    if (target.is_current) {
      await store.logout()
      ElMessage.success('已退出当前设备')
      router.push('/login')
    } else {
      await auth.revokeDevice(store.token, id)
      devices.value = devices.value.filter(d => d.id !== id)
      ElMessage.success('该设备已登出')
    }
  } catch (e) {
    ElMessage.error('登出失败')
  }
}

function openQuick(action: 'profile'|'display'|'play'|'notify') {
  // 跳转至对应路由
  switch (action) {
    case 'profile': router.push('/user/profile'); break
    case 'display': router.push('/user/settings/display'); break
    case 'play': router.push('/user/settings/player'); break
    case 'notify': router.push('/user/settings/notify'); break
  }
}

async function exportMyData() {
  // TODO: 触发后端数据导出任务
  ElMessage.success('已开始导出，完成后将通知您')
}

async function deleteAccount() {
  try {
    await ElMessageBox.confirm(
      '删除账户将清空您的数据且不可恢复，确认继续？',
      '删除账户确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
    // TODO: 调用后端删除账户接口
    ElMessage.success('账户删除请求已提交')
  } catch {
    ElMessage.info('已取消删除')
  }
}

onMounted(() => {
  refreshDevices()
})

function parseUA(ua?: string) {
  const text = ua || ''
  let os = ''
  if (/Mac OS X/i.test(text)) os = 'macOS'
  else if (/Windows NT/i.test(text)) os = 'Windows'
  else if (/Android/i.test(text)) os = 'Android'
  else if (/(iPhone|iPad|iPod)/i.test(text)) os = 'iOS'
  else if (/Linux/i.test(text)) os = 'Linux'

  let browser = ''
  let version = ''
  const mEdge = text.match(/Edg\/(\d+)/i)
  const mChrome = text.match(/Chrome\/(\d+)/i)
  const mFirefox = text.match(/Firefox\/(\d+)/i)
  const mSafariVersion = !mChrome && !mEdge ? text.match(/Version\/(\d+)/i) : null
  if (mEdge) { browser = 'Edge'; version = mEdge[1] }
  else if (mChrome) { browser = 'Chrome'; version = mChrome[1] }
  else if (mFirefox) { browser = 'Firefox'; version = mFirefox[1] }
  else if (mSafariVersion) { browser = 'Safari'; version = mSafariVersion[1] }

  const mTrae = text.match(/Trae\/(\d+(?:\.\d+)*)/i)
  const mElectron = text.match(/Electron\/(\d+(?:\.\d+)*)/i)

  return { os, browser, version, trae: !!mTrae, traeVer: mTrae?.[1], electron: !!mElectron, electronVer: mElectron?.[1] }
}

function formatAgent(d: any) {
  const info = parseUA(d.ua)
  const parts: string[] = []
  if (info.os) parts.push(info.os)
  if (info.trae) parts.push('Trae')
  if (info.browser) parts.push(info.version ? `${info.browser} ${info.version}` : info.browser)
  if (info.electron) parts.push(info.electronVer ? `Electron ${info.electronVer}` : 'Electron')
  if (!parts.length) return (d.alias ?? '未知')
  return parts.join(' · ')
}
</script>

<template>
  <div class="user-page content">
    <!-- 用户总览 -->
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">用户总览</h3>
        <div class="section-meta text-muted">当前用户：{{ username }}</div>
      </div>
      <div class="quick-grid">
        <button class="quick-card card card--hover" @click="openQuick('profile')" aria-label="个人信息">
          <span class="quick-title">个人信息</span>
        </button>
        <button class="quick-card card card--hover" @click="openQuick('display')" aria-label="显示设置">
          <span class="quick-title">显示设置</span>
        </button>
        <button class="quick-card card card--hover" @click="openQuick('play')" aria-label="播放设置">
          <span class="quick-title">播放设置</span>
        </button>
        <button class="quick-card card card--hover" @click="openQuick('notify')" aria-label="通知设置">
          <span class="quick-title">通知设置</span>
        </button>
      </div>
    </section>

    <!-- 管理专用（仅管理员可见） -->
    <section v-if="isAdmin" class="card section">
      <div class="section-header">
        <h3 class="section-title">管理专用</h3>
        <span class="admin-tag" aria-label="管理员">Admin</span>
      </div>
      <div class="quick-grid">
        <button class="quick-card card card--hover" @click="router.push('/admin/console')">
          <span class="quick-title">控制台</span>
          <span class="quick-sub text-muted">管理员入口</span>
        </button>
        <button class="quick-card card card--hover" @click="router.push('/admin/dashboard')">
          <span class="quick-title">数据看板</span>
          <span class="quick-sub text-muted">概览与监控</span>
        </button>
        <button class="quick-card card card--hover" @click="router.push('/admin/users')">
          <span class="quick-title">用户管理</span>
          <span class="quick-sub text-muted">角色与权限</span>
        </button>
        <button class="quick-card card card--hover" @click="router.push('/admin/libraries')">
          <span class="quick-title">媒体库管理</span>
          <span class="quick-sub text-muted">源与索引</span>
        </button>
      </div>
    </section>

    <!-- 登录设备 -->
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">登录记录（最近活动）</h3>
        <div class="actions">
          <button class="btn btn--ghost btn--sm" :disabled="loadingDevices" @click="refreshDevices">刷新记录</button>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>设备 / 浏览器</th>
              <th>登录时间</th>
              <th>IP / 位置</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in devices" :key="d.id">
              <td>
                <el-tooltip placement="top" effect="dark">
                  <template #content>
                    <div class="ua-tip">
                      <div>别名：{{ d.alias ?? '未知' }}</div>
                      <div>平台：{{ d.platform ?? '-' }}</div>
                      <div>UA：{{ d.ua ?? '-' }}</div>
                      <div>时间：{{ d.time }}</div>
                      <div>IP：{{ d.ip }}</div>
                    </div>
                  </template>
                  <span class="ua-text">{{ formatAgent(d) }}</span>
                </el-tooltip>
              </td>
              <td>{{ d.time }}</td>
              <td>{{ d.ip }}</td>
              <td>
                <button class="btn btn--danger btn--sm" @click="logoutDevice(d.id)">登出</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 账户操作 -->
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">账户操作</h3>
      </div>
      <div class="actions cluster wrap">
        <button class="btn btn--primary btn--lg" @click="exportMyData">导出我的数据</button>
        <button class="btn btn--danger btn--lg" @click="deleteAccount">删除账户（二次确认）</button>
      </div>
      <p class="hint text-muted">请谨慎操作。删除账户会清空数据并不可恢复。</p>
    </section>
  </div>
</template>

<style scoped>
.user-page { padding-block: var(--space-5); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.section + .section { margin-top: var(--space-5); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.section-title { font-size: var(--text-lg); font-weight: 600; margin: 0; }

.quick-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--gap); }
.quick-card { display: grid; place-items: center; text-align: center; padding: var(--space-6); cursor: pointer; }
.quick-title { font-weight: 600; color: var(--text-primary); }
.quick-sub { font-size: var(--text-xs); }
.admin-tag { display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: var(--radius-pill); background: color-mix(in oklab, var(--brand), white 85%); color: var(--text-secondary); border: 1px solid color-mix(in oklab, var(--brand), black 10%); }

.table-wrap { overflow: auto; border-radius: var(--radius-md); }
.table-wrap table { background: var(--surface); border-radius: var(--radius-md); }
.table-wrap th, .table-wrap td { white-space: nowrap; }

.ua-text { max-width: 280px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }

.hint { margin-top: var(--space-2); }

@media (max-width: 768px) {
  .section { padding: var(--space-5); }
}
</style>