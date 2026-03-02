import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { users } from '@/api'
import type {
  UserRead,
  UserRole,
  UserCreateRequestSchema,
  UserUpdateRequestSchema,
  UserPageResult,
  UserPasswordReset,
  UserPasswordChange,
  UserIdentityUpdate,
} from '@/types/user'
import type { ListUsersParams } from '@/api/users'

export const useUsersStore = defineStore('users', () => {
  // 规范化字典与列表
  const entities = ref<Record<string, UserRead>>({})
  const list = ref<UserRead[]>([])
  const listMeta = ref({ page: 1, size: 20, total: 0, pages: 0 })

  // 列表筛选（与后端参数一致）
  const filters = ref<ListUsersParams>({
    page: 1,
    size: 20,
    query: undefined,
    role: undefined,
    is_active: undefined,
    is_verified: undefined,
  })

  // 当前选择用户
  const currentId = ref<string | null>(null)
  const currentUser = computed<UserRead | null>(() => {
    const id = currentId.value
    return id ? entities.value[id] ?? list.value.find((u) => u.id === id) ?? null : null
  })

  // 通用状态
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 列表查询
  async function fetchList(
    token: string,
    partial?: Partial<ListUsersParams>,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const params: ListUsersParams = { ...filters.value, ...(partial ?? {}) }
      const res: UserPageResult = await users.listUsers(token, params, options)
      list.value = res.items
      listMeta.value = { page: res.page, size: res.size, total: res.total, pages: res.pages }
      // 写回规范化字典
      const merged: Record<string, UserRead> = { ...entities.value }
      for (const item of res.items) merged[item.id] = item
      entities.value = merged
      return res
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 详情查询
  async function fetchById(
    token: string,
    userId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const u = await users.getUser(token, userId, options)
      entities.value = { ...entities.value, [u.id]: u }
      currentId.value = u.id
      return u
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 创建用户
  async function create(
    token: string,
    payload: UserCreateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const u = await users.createUser(token, payload, options)
      entities.value = { ...entities.value, [u.id]: u }
      list.value = [u, ...list.value]
      return u
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 更新用户（设置/其他允许的字段）
  async function update(
    token: string,
    userId: string,
    patch: UserUpdateRequestSchema,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const u = await users.updateUser(token, userId, patch, options)
      entities.value = { ...entities.value, [u.id]: u }
      const idx = list.value.findIndex((i) => i.id === u.id)
      if (idx >= 0) list.value.splice(idx, 1, u)
      return u
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 删除用户（默认软删） -> 对齐 API：不再接收 softDelete，返回 { message, success }
  async function remove(
    token: string,
    userId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const res = await users.deleteUser(token, userId, options)
      const idx = list.value.findIndex((i) => i.id === userId)
      if (idx >= 0) list.value.splice(idx, 1)
      const next = { ...entities.value }
      delete next[userId]
      entities.value = next
      if (currentId.value === userId) currentId.value = null
      return res
    } catch (e: unknown) {
      if (e instanceof Error) error.value = e.message
      else error.value = String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 启停（激活状态）
  async function setActive(
    token: string,
    userId: string,
    isActive: boolean,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const u = await users.setUserActive(token, userId, isActive, options)
    entities.value = { ...entities.value, [u.id]: u }
    const idx = list.value.findIndex((i) => i.id === u.id)
    if (idx >= 0) list.value.splice(idx, 1, u)
    return u
  }

  // 角色与权限
  async function setRole(
    token: string,
    userId: string,
    role: UserRole,
    permissions?: string[] | null,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const u = await users.setRolePermissions(token, userId, role, permissions, options)
    entities.value = { ...entities.value, [u.id]: u }
    const idx = list.value.findIndex((i) => i.id === u.id)
    if (idx >= 0) list.value.splice(idx, 1, u)
    return u
  }

  // 密码重置
  async function resetPassword(
    token: string,
    userId: string,
    payload: UserPasswordReset,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const u = await users.resetPassword(token, userId, payload, options)
    entities.value = { ...entities.value, [u.id]: u }
    const idx = list.value.findIndex((i) => i.id === u.id)
    if (idx >= 0) list.value.splice(idx, 1, u)
    return u
  }

  // 密码修改
  async function changePassword(
    token: string,
    userId: string,
    payload: UserPasswordChange,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const u = await users.changePassword(token, userId, payload, options)
    entities.value = { ...entities.value, [u.id]: u }
    const idx = list.value.findIndex((i) => i.id === u.id)
    if (idx >= 0) list.value.splice(idx, 1, u)
    return u
  }

  // 身份信息更新（用户名/邮箱）
  async function updateIdentity(
    token: string,
    userId: string,
    payload: UserIdentityUpdate,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const u = await users.updateIdentity(token, userId, payload, options)
    entities.value = { ...entities.value, [u.id]: u }
    const idx = list.value.findIndex((i) => i.id === u.id)
    if (idx >= 0) list.value.splice(idx, 1, u)
    return u
  }

  // Router ping（健康检查）
  async function pingRouter(options?: { baseURL?: string; signal?: AbortSignal }) {
    return users.ping(options)
  }

  // 辅助：筛选、选择、清理
  function setFilters(partial?: Partial<ListUsersParams>) {
    filters.value = { ...filters.value, ...(partial ?? {}) }
  }

  function select(userId: string | null) {
    currentId.value = userId
  }

  function clearList() {
    list.value = []
    listMeta.value = { page: 1, size: filters.value.size ?? 20, total: 0, pages: 0 }
  }

  // 新增：批量获取用户ID映射
  async function getMapping(
    token: string,
    ids: string[],
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    return users.getUserMapping(token, ids, options)
  }

  // 新增：批量获取头像签名
  async function getProfilesSigned(
    token: string,
    ids: string[],
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    return users.getUserProfilesSigned(token, ids, options)
  }

  // 上传用户头像（成功后刷新当前用户信息）
  async function uploadProfile(
    token: string,
    userId: string,
    file: File,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    const res = await users.uploadUserProfile(token, userId, file, options)
    if (res.ok) {
      await fetchById(token, userId, options)
    }
    return res
  }

  return {
    entities,
    list,
    listMeta,
    filters,
    currentId,
    currentUser,
    loading,
    error,
    fetchList,
    fetchById,
    create,
    update,
    remove,
    setActive,
    setRole,
    resetPassword,
    changePassword,
    updateIdentity,
    pingRouter,
    getMapping,
    getProfilesSigned,
    uploadProfile,
    setFilters,
    select,
    clearList,
  }
})