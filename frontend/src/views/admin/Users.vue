<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ListToolbar from '@/components/ui/ListToolbar.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import { useUserStore } from '@/stores/user'
import { useUsersStore } from '@/stores/users'
import { useOpsLogStore } from '@/stores/ops_log'
import type { UserRole } from '@/types/user'

const userStore = useUserStore()
const users = useUsersStore()
const ops = useOpsLogStore()

const quick = ref('')
const showFilterDialog = ref(false)
const showSortDialog = ref(false)
const filterForm = ref<{ role: UserRole | null; is_active: boolean | null; is_verified: boolean | null }>({ role: null, is_active: null, is_verified: null })
const sortBy = ref<'last_login_at' | 'created_at' | null>(null)
const sortOrder = ref<'asc' | 'desc'>('desc')
const showCreateDialog = ref(false)
const createForm = ref<{ username: string; email: string; password: string; role: UserRole | null; permissions: string; is_active: boolean; is_verified: boolean; settings: { theme: string; language: string; auto_play: boolean; subtitle_enabled: boolean; quality_preference: string } }>({
  username: '',
  email: '',
  password: '',
  role: null,
  permissions: '',
  is_active: true,
  is_verified: true,
  settings: { theme: 'system', language: 'zh-CN', auto_play: true, subtitle_enabled: true, quality_preference: 'auto' },
})
const showDetail = ref(false)
const showEdit = ref(false)
const showDetailDialog = ref(false)
const showEditDialog = ref(false)
const activeEditKey = ref<'identity' | 'password' | 'role' | 'settings'>('identity')
const identityForm = ref<{ username: string | null; email: string | null }>({ username: null, email: null })
const passwordForm = ref<{ new_password: string }>({ new_password: '' })
const roleForm = ref<{ role: UserRole | null; permissions: string }>({ role: null, permissions: '' })
const settingsForm = ref<{ theme: string; language: string; auto_play: boolean; subtitle_enabled: boolean; quality_preference: string }>({ theme: 'system', language: 'zh-CN', auto_play: true, subtitle_enabled: true, quality_preference: 'auto' })
const roleInput = ref<UserRole | null>(null)

onMounted(() => { users.fetchList(userStore.token ?? '', { page: 1, size: 20 }).catch(()=>{}) })

function onSearch(q: string) {
  quick.value = q
  users.fetchList(userStore.token ?? '', { query: q, page: 1 }).catch(()=>{})
}

function openFilterDialog() {
  filterForm.value.role = users.filters.role ?? null as any
  filterForm.value.is_active = users.filters.is_active ?? null
  filterForm.value.is_verified = users.filters.is_verified ?? null
  showFilterDialog.value = true
}

function applyFilter() {
  users.setFilters({ role: filterForm.value.role ?? undefined, is_active: filterForm.value.is_active ?? undefined, is_verified: filterForm.value.is_verified ?? undefined })
  users.fetchList(userStore.token ?? '', { page: 1 }).catch(()=>{})
  showFilterDialog.value = false
}

function clearFilter() {
  filterForm.value = { role: null, is_active: null, is_verified: null }
}

function openSortDialog() { showSortDialog.value = true }

const tableData = computed(() => {
  const data = [...users.list]
  if (!sortBy.value) return data
  const key = sortBy.value
  const dir = sortOrder.value
  return data.sort((a: any, b: any) => {
    const av = a?.[key] ?? null
    const bv = b?.[key] ?? null
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    const ai = typeof av === 'string' ? Date.parse(av) || 0 : av
    const bi = typeof bv === 'string' ? Date.parse(bv) || 0 : bv
    return dir === 'asc' ? ai - bi : bi - ai
  })
})

function openCreateDialog() {
  showCreateDialog.value = true
}

async function submitCreate() {
  const username = createForm.value.username?.trim()
  const email = createForm.value.email?.trim()
  const password = createForm.value.password
  const role = createForm.value.role
  if (!username || !email || !password || !role) return
  const perms = createForm.value.permissions.split(',').map((s)=>s.trim()).filter(Boolean)
  const payload = {
    username,
    email,
    role,
    permissions: perms,
    is_active: createForm.value.is_active,
    is_verified: createForm.value.is_verified,
    settings: { ...createForm.value.settings },
    password,
  }
  try {
    const u = await users.create(userStore.token ?? '', payload)
    showCreateDialog.value = false
    createForm.value = {
      username: '',
      email: '',
      password: '',
      role: null,
      permissions: '',
      is_active: true,
      is_verified: true,
      settings: { theme: 'system', language: 'zh-CN', auto_play: true, subtitle_enabled: true, quality_preference: 'auto' },
    }
    ElMessage.success('已创建用户')
    ops.add({ user: userStore.user?.username ?? null, action: 'create-user', target: u.id, result: 'success' })
  } catch (e) {
    ops.add({ user: userStore.user?.username ?? null, action: 'create-user', result: 'error' })
  }
}

async function removeUser(id: string) {
  try {
    await ElMessageBox.confirm('删除后不可恢复，确认删除该用户？', '删除用户', { type: 'warning' })
    const res = await users.remove(userStore.token ?? '', id)
    ElMessage.success(res.message ?? '已删除')
    ops.add({ user: userStore.user?.username ?? null, action: 'delete-user', target: id, result: 'success' })
  } catch (e) {
    if (e) { ops.add({ user: userStore.user?.username ?? null, action: 'delete-user', target: id, result: 'cancel' }) }
  }
}

async function resetPassword(id: string) {
  try {
    await ElMessageBox.confirm('将重置该用户密码，确认？', '重置密码', { type: 'warning' })
    await users.resetPassword(userStore.token ?? '', id, { new_password: passwordForm.value.new_password })
    ElMessage.success('已重置密码')
    ops.add({ user: userStore.user?.username ?? null, action: 'reset-password', target: id, result: 'success' })
  } catch {
    ops.add({ user: userStore.user?.username ?? null, action: 'reset-password', target: id, result: 'cancel' })
  }
}

async function changeRole(id: string, role: UserRole) {
  try {
    await ElMessageBox.confirm(`确认将该用户角色设置为 ${role}？`, '修改角色', { type: 'warning' })
    const perms = roleForm.value.permissions.split(',').map(s=>s.trim()).filter(Boolean)
    await users.setRole(userStore.token ?? '', id, role, perms.length ? perms : null)
    ElMessage.success('角色已更新')
    ops.add({ user: userStore.user?.username ?? null, action: 'set-role', target: id, result: 'success' })
  } catch {
    ops.add({ user: userStore.user?.username ?? null, action: 'set-role', target: id, result: 'cancel' })
  }
}

function openDetail(userId: string) {
  users.fetchById(userStore.token ?? '', userId).then(() => {
    showDetailDialog.value = true
  }).catch(()=>{})
}

function openEdit(userId: string) {
  users.fetchById(userStore.token ?? '', userId).then(() => {
    const u = users.currentUser
    identityForm.value.username = u?.username ?? null
    identityForm.value.email = u?.email ?? null
    passwordForm.value.new_password = ''
    roleForm.value.role = u?.role ?? null
    roleForm.value.permissions = (u?.permissions ?? []).join(',')
    settingsForm.value = {
      theme: u?.settings?.theme ?? 'system',
      language: u?.settings?.language ?? 'zh-CN',
      auto_play: u?.settings?.auto_play ?? true,
      subtitle_enabled: u?.settings?.subtitle_enabled ?? true,
      quality_preference: u?.settings?.quality_preference ?? 'auto',
    }
    activeEditKey.value = 'identity'
    showEditDialog.value = true
  }).catch(()=>{})
}

async function submitIdentity() {
  const id = users.currentUser?.id
  if (!id) return
  await users.updateIdentity(userStore.token ?? '', id, { username: identityForm.value.username, email: identityForm.value.email }).then(()=>{
    ElMessage.success('已更新用户名 / 邮箱')
    users.fetchById(userStore.token ?? '', id).catch(()=>{})
  })
}

async function submitPassword() {
  const id = users.currentUser?.id
  if (!id) return
  await users.resetPassword(userStore.token ?? '', id, { new_password: passwordForm.value.new_password }).then(()=>{
    ElMessage.success('已重置密码')
    users.fetchById(userStore.token ?? '', id).catch(()=>{})
  })
}

async function submitRole() {
  const id = users.currentUser?.id
  if (!id || !roleForm.value.role) return
  const perms = roleForm.value.permissions.split(',').map(s=>s.trim()).filter(Boolean)
  await users.setRole(userStore.token ?? '', id, roleForm.value.role, perms.length ? perms : null).then(()=>{
    ElMessage.success('已更新角色 / 权限')
    users.fetchById(userStore.token ?? '', id).catch(()=>{})
  })
}

async function submitSettings() {
  const id = users.currentUser?.id
  if (!id) return
  await users.update(userStore.token ?? '', id, { settings: { ...settingsForm.value } }).then(()=>{
    ElMessage.success('已更新用户设置')
    users.fetchById(userStore.token ?? '', id).catch(()=>{})
  })
}

</script>

<template>
  <div class="admin-users">
    <ListToolbar :viewMode="'list'" :disableViewToggle="true" :add-handler="openCreateDialog" @search="onSearch" @open-filter="openFilterDialog" @open-sort="openSortDialog" />

    <section class="card section">
      <div class="table-wrap">
        <el-table :data="tableData" size="small" style="width: 100%">
          <el-table-column prop="id" label="ID" width="160" />
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="email" label="邮箱" />
          <el-table-column prop="role" label="角色" width="120" />
          <el-table-column prop="is_active" label="活跃" width="100" />
          <el-table-column prop="is_verified" label="已验证" width="100" />
          <el-table-column label="操作" width="300">
            <template #default="{ row }">
              <el-button size="small" @click="openDetail(row.id)">详情</el-button>
              <el-button size="small" type="primary" @click="openEdit(row.id)">编辑</el-button>
              <el-button size="small" type="danger" @click="removeUser(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <PaginationBar :page="users.listMeta.page" :pageSize="users.listMeta.size" :total="users.listMeta.total" @change="(p:number)=>users.fetchList(userStore.token ?? '', { page: p })" />
    </section>

    <el-dialog v-model="showFilterDialog" title="筛选" width="520px">
      <el-form label-width="96px" :model="filterForm">
        <el-form-item label="身份">
          <el-select v-model="filterForm.role" placeholder="选择角色" style="width: 200px">
            <el-option label="全部" :value="null" />
            <el-option label="admin" value="admin" />
            <el-option label="user" value="user" />
            <el-option label="guest" value="guest" />
          </el-select>
        </el-form-item>
        <el-form-item label="活跃">
          <el-select v-model="filterForm.is_active" placeholder="全部" style="width: 200px">
            <el-option label="全部" :value="null" />
            <el-option label="是" :value="true" />
            <el-option label="否" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="已验证">
          <el-select v-model="filterForm.is_verified" placeholder="全部" style="width: 200px">
            <el-option label="全部" :value="null" />
            <el-option label="是" :value="true" />
            <el-option label="否" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="clearFilter">清空</el-button>
          <el-button type="primary" @click="applyFilter">应用</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog v-model="showSortDialog" title="排序" width="520px">
      <el-form label-width="96px">
        <el-form-item label="排序字段">
          <el-select v-model="sortBy" placeholder="选择字段" style="width: 240px">
            <el-option label="最后登录时间" value="last_login_at" />
            <el-option label="创建时间" value="created_at" />
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

    <el-dialog v-model="showCreateDialog" title="新增用户" width="760px">
      <el-form label-width="96px" :model="createForm">
        <el-form-item label="用户名"><el-input v-model="createForm.username" placeholder="输入用户名" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="createForm.email" placeholder="输入邮箱" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="createForm.password" type="password" placeholder="输入初始密码" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" placeholder="选择角色" style="width: 200px">
            <el-option label="admin" value="admin" />
            <el-option label="user" value="user" />
            <el-option label="guest" value="guest" />
          </el-select>
        </el-form-item>
        <el-form-item label="权限"><el-input v-model="createForm.permissions" placeholder="逗号分隔，如 manage,read" /></el-form-item>
        <el-form-item label="活跃"><el-switch v-model="createForm.is_active" /></el-form-item>
        <el-form-item label="已验证"><el-switch v-model="createForm.is_verified" /></el-form-item>
        <el-form-item label="主题"><el-input v-model="createForm.settings.theme" placeholder="system/light/dark" /></el-form-item>
        <el-form-item label="语言"><el-input v-model="createForm.settings.language" placeholder="如 zh-CN" /></el-form-item>
        <el-form-item label="自动播放"><el-switch v-model="createForm.settings.auto_play" /></el-form-item>
        <el-form-item label="字幕启用"><el-switch v-model="createForm.settings.subtitle_enabled" /></el-form-item>
        <el-form-item label="画质偏好"><el-input v-model="createForm.settings.quality_preference" placeholder="auto/1080p/720p" /></el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="users.loading" :disabled="!createForm.username || !createForm.email || !createForm.password || !createForm.role" @click="submitCreate">创建</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>

    <el-dialog v-model="showDetailDialog" title="用户详情" width="640px">
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="ID">{{ users.currentUser?.id }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ users.currentUser?.username }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ users.currentUser?.email }}</el-descriptions-item>
        <el-descriptions-item label="角色">{{ users.currentUser?.role }}</el-descriptions-item>
        <el-descriptions-item label="权限">{{ (users.currentUser?.permissions ?? []).join(',') }}</el-descriptions-item>
        <el-descriptions-item label="活跃">{{ users.currentUser?.is_active }}</el-descriptions-item>
        <el-descriptions-item label="已验证">{{ users.currentUser?.is_verified }}</el-descriptions-item>
        <el-descriptions-item label="最后登录">{{ users.currentUser?.last_login_at }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ users.currentUser?.created_at }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ users.currentUser?.updated_at }}</el-descriptions-item>
        <el-descriptions-item label="设置"><pre style="white-space: pre-wrap; margin: 0">{{ JSON.stringify(users.currentUser?.settings ?? {}, null, 2) }}</pre></el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑用户" width="760px">
      <div class="edit-layout">
        <el-menu :default-active="activeEditKey" class="edit-menu" @select="(k:string)=>activeEditKey=k as any">
          <el-menu-item index="identity">更改用户名 / 邮箱</el-menu-item>
          <el-menu-item index="password">重置密码</el-menu-item>
          <el-menu-item index="role">更改角色 / 权限</el-menu-item>
          <el-menu-item index="settings">更改用户设置</el-menu-item>
        </el-menu>
        <div class="edit-form">
          <div v-if="activeEditKey==='identity'" class="form-pane">
            <el-form label-width="96px" :model="identityForm">
              <el-form-item label="用户名"><el-input v-model="identityForm.username" placeholder="输入新用户名" /></el-form-item>
              <el-form-item label="邮箱"><el-input v-model="identityForm.email" placeholder="输入新邮箱" /></el-form-item>
              <el-form-item><el-button type="primary" @click="submitIdentity">保存</el-button></el-form-item>
            </el-form>
          </div>
          <div v-else-if="activeEditKey==='password'" class="form-pane">
            <el-form label-width="96px" :model="passwordForm">
              <el-form-item label="新密码"><el-input v-model="passwordForm.new_password" type="password" placeholder="输入新密码" /></el-form-item>
              <el-form-item><el-button type="primary" @click="submitPassword">重置密码</el-button></el-form-item>
            </el-form>
          </div>
          <div v-else-if="activeEditKey==='role'" class="form-pane">
            <el-form label-width="96px" :model="roleForm">
              <el-form-item label="角色">
                <el-select v-model="roleForm.role" placeholder="选择角色" style="width: 200px">
                  <el-option label="admin" value="admin" />
                  <el-option label="user" value="user" />
                  <el-option label="guest" value="guest" />
                </el-select>
              </el-form-item>
              <el-form-item label="权限">
                <el-input v-model="roleForm.permissions" placeholder="逗号分隔的权限，如 manage,read" />
              </el-form-item>
              <el-form-item><el-button type="primary" @click="submitRole">保存</el-button></el-form-item>
            </el-form>
          </div>
          <div v-else class="form-pane">
            <el-form label-width="120px" :model="settingsForm">
              <el-form-item label="主题"><el-input v-model="settingsForm.theme" placeholder="system/light/dark" /></el-form-item>
              <el-form-item label="语言"><el-input v-model="settingsForm.language" placeholder="如 zh-CN" /></el-form-item>
              <el-form-item label="自动播放"><el-switch v-model="settingsForm.auto_play" /></el-form-item>
              <el-form-item label="字幕启用"><el-switch v-model="settingsForm.subtitle_enabled" /></el-form-item>
              <el-form-item label="画质偏好"><el-input v-model="settingsForm.quality_preference" placeholder="auto/1080p/720p" /></el-form-item>
              <el-form-item><el-button type="primary" @click="submitSettings">保存</el-button></el-form-item>
            </el-form>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-users { padding: var(--space-6); display: grid; gap: var(--space-5); }
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

.edit-layout { display: grid; grid-template-columns: 200px 1fr; gap: var(--space-5); }
.edit-menu { border-right: 1px solid var(--border); }
.form-pane { background: var(--surface); padding: var(--space-5); border-radius: var(--radius-md); }
</style>
