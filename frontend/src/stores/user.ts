import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { auth } from '@/api'
import { useMovieStore } from './movie'
import { useUserCollectionsStore } from './user_collections'
import type { UserRead, UserRole } from '@/types/user'
import type { RegisterPayload, LoginPayload } from '@/api/auth'

const STORAGE_TOKEN_KEY = 'lotusdb.token'
const STORAGE_USER_KEY = 'lotusdb.user'

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message
  if (typeof e === 'string') return e
  try {
    return JSON.stringify(e)
  } catch {
    return String(e)
  }
}

export const useUserStore = defineStore('user', () => {
  // 基本状态
  const token = ref<string | null>(null)
  const user = ref<UserRead | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 计算属性
  const isAuthenticated = computed<boolean>(() => !!token.value)
  const roles = computed<UserRole[]>(() => (user.value ? [user.value.role] : []))
  const permissions = computed<string[]>(() => user.value?.permissions ?? [])

  // 工具：本地持久化
  function persist() {
    try {
      if (token.value) {
        localStorage.setItem(STORAGE_TOKEN_KEY, token.value)
      } else {
        localStorage.removeItem(STORAGE_TOKEN_KEY)
      }
      if (user.value) {
        localStorage.setItem(STORAGE_USER_KEY, JSON.stringify(user.value))
      } else {
        localStorage.removeItem(STORAGE_USER_KEY)
      }
    } catch {}
  }

  function hydrateFromStorage() {
    try {
      const t = localStorage.getItem(STORAGE_TOKEN_KEY)
      token.value = t && t.length > 0 ? t : null
      const u = localStorage.getItem(STORAGE_USER_KEY)
      user.value = u ? (JSON.parse(u) as UserRead) : null
    } catch {
      token.value = null
      user.value = null
    }
  }

  function clearStorage() {
    try {
      localStorage.removeItem(STORAGE_TOKEN_KEY)
      localStorage.removeItem(STORAGE_USER_KEY)
    } catch {}
  }

  // 权限判断
  function hasRole(role: UserRole): boolean {
    return roles.value.includes(role)
  }

  function hasPermission(perm: string): boolean {
    return permissions.value.includes(perm)
  }

  // 登录 / 注册 / 注销
  async function register(
    payload: RegisterPayload,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const res = await auth.register<UserRead>(payload, options)
      token.value = res.access_token
      user.value = res.user
      persist()
      return res
    } catch (e: unknown) {
      error.value = toMessage(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function login(
    payload: LoginPayload,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    loading.value = true
    error.value = null
    try {
      const res = await auth.login<UserRead>(payload, options)
      token.value = res.access_token
      user.value = res.user
      persist()
      const m = useMovieStore()
      const c = useUserCollectionsStore()
      m.setCurrentMovie(null)
      m.clearCollectionIds()
      c.clearList()
      c.clearMovies()
      return res
    } catch (e: unknown) {
      error.value = toMessage(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function logout(options?: { baseURL?: string; signal?: AbortSignal }) {
    loading.value = true
    error.value = null
    try {
      if (token.value) {
        await auth.logout(token.value, options)
      }
      token.value = null
      user.value = null
      clearStorage()
      const m = useMovieStore()
      const c = useUserCollectionsStore()
      m.setCurrentMovie(null)
      m.clearCollectionIds()
      c.clearList()
      c.clearMovies()
    } catch (e: unknown) {
      // 即使后端报错，也清理本地状态，但暴露错误信息
      error.value = toMessage(e)
      token.value = null
      user.value = null
      clearStorage()
      const m = useMovieStore()
      const c = useUserCollectionsStore()
      m.setCurrentMovie(null)
      m.clearCollectionIds()
      c.clearList()
      c.clearMovies()
      throw e
    } finally {
      loading.value = false
    }
  }

  // store 初始化时尝试从本地恢复
  hydrateFromStorage()

  // 设备会话列表
  async function listDevices(options?: { baseURL?: string; signal?: AbortSignal }) {
    if (!token.value) throw new Error('未登录')
    loading.value = true
    error.value = null
    try {
      return await auth.listDevices(token.value, options)
    } catch (e: unknown) {
      error.value = toMessage(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 撤销指定设备
  async function revokeDevice(
    sessionId: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    if (!token.value) throw new Error('未登录')
    loading.value = true
    error.value = null
    try {
      return await auth.revokeDevice(token.value, sessionId, options)
    } catch (e: unknown) {
      error.value = toMessage(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 撤销除当前外的所有设备
  async function revokeAllDevices(options?: { baseURL?: string; signal?: AbortSignal }) {
    if (!token.value) throw new Error('未登录')
    loading.value = true
    error.value = null
    try {
      return await auth.revokeAllDevices(token.value, options)
    } catch (e: unknown) {
      error.value = toMessage(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 重命名设备会话
  async function renameDevice(
    sessionId: string,
    alias: string,
    options?: { baseURL?: string; signal?: AbortSignal }
  ) {
    if (!token.value) throw new Error('未登录')
    loading.value = true
    error.value = null
    try {
      return await auth.renameDevice(token.value, sessionId, alias, options)
    } catch (e: unknown) {
      error.value = toMessage(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    token,
    user,
    loading,
    error,
    isAuthenticated,
    roles,
    permissions,
    hasRole,
    hasPermission,
    register,
    login,
    logout,
    hydrateFromStorage,
    clearStorage,
    listDevices,
    revokeDevice,
    revokeAllDevices,
    renameDevice,
  }
})
