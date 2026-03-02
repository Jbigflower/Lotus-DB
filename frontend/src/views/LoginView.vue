<template>
  <div class="auth-page">
    <div class="auth-card">
      <header class="auth-header">
        <h1 class="brand">Lotus DB</h1>
        <button class="theme-toggle" @click="toggleTheme" :title="isDark ? '切换到日间' : '切换到夜间'">
          <span v-if="isDark">🌙</span>
          <span v-else>☀️</span>
        </button>
      </header>

      <div class="tabs">
        <button class="tab" :class="{ active: activeTab === 'login' }" @click="activeTab = 'login'">登录</button>
        <button class="tab" :class="{ active: activeTab === 'register' }" @click="activeTab = 'register'">注册</button>
      </div>

      <div class="error" v-if="error">{{ error }}</div>

      <!-- 修复：只使用 el-form，不再嵌套原生 form -->
      <el-form v-if="activeTab === 'login'" :model="loginForm" label-position="top" class="el-reset" @submit.prevent="onLogin">
        <el-form-item label="邮箱或用户名">
          <el-input v-model="loginForm.username" autocomplete="username" placeholder="请输入邮箱或用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="loginForm.password" type="password" autocomplete="current-password" placeholder="请输入密码" />
        </el-form-item>
        <el-button type="primary" :loading="loading" class="submit" native-type="submit">登录</el-button>
      </el-form>

      <el-form v-else :model="registerForm" label-position="top" class="el-reset" @submit.prevent="onRegister">
        <el-form-item label="用户名" :error="usernameError">
          <el-input v-model="registerForm.username" autocomplete="username" placeholder="请输入用户名" @input="debouncedCheckUsername" />
        </el-form-item>
        <el-form-item label="邮箱" :error="emailError">
          <el-input v-model="registerForm.email" autocomplete="email" placeholder="name@example.com" @input="debouncedCheckEmail" />
        </el-form-item>
        <el-form-item label="密码" :error="passwordError">
          <el-input v-model="registerForm.password" type="password" autocomplete="new-password" placeholder="至少 8 位" />
        </el-form-item>
        <el-button type="primary" :loading="loading" class="submit" native-type="submit">注册</el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, watchEffect } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { auth } from '@/api'
import { useTheme } from '@/composables/useTheme'

const { isDark, toggleTheme } = useTheme()
const router = useRouter()
const route = useRoute()
const store = useUserStore()

const activeTab = ref<'login' | 'register'>('login')
const loading = computed(() => store.loading)
const error = computed(() => store.error)
const isAuthenticated = computed(() => store.isAuthenticated)
const redirect = computed(() => {
  const r = route.query?.redirect
  return typeof r === 'string' && r ? decodeURIComponent(r) : '/'
})

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', email: '', password: '' })

const usernameError = ref<string | null>(null)
const emailError = ref<string | null>(null)
const passwordError = ref<string | null>(null)

function clearRegisterErrors() { usernameError.value = null; emailError.value = null; passwordError.value = null }

let userTimer: number | null = null
let emailTimer: number | null = null
function debounce(fn: () => void, delay = 300, slot: 'user' | 'email' = 'user') {
  const timer = slot === 'user' ? userTimer : emailTimer
  if (timer) window.clearTimeout(timer)
  const newTimer = window.setTimeout(fn, delay)
  if (slot === 'user') userTimer = newTimer; else emailTimer = newTimer
}

function debouncedCheckUsername() {
  usernameError.value = null
  const v = registerForm.username?.trim()
  if (!v) return
  if (v.length < 2) { usernameError.value = '用户名至少 2 位'; return }
  debounce(async () => {
    try { const res = await auth.checkUsernameAvailability(v); usernameError.value = res.available ? null : '用户名已被占用' }
    catch { usernameError.value = '用户名校验失败' }
  }, 400, 'user')
}

function debouncedCheckEmail() {
  emailError.value = null
  const v = registerForm.email?.trim()
  if (!v) return
  if (!/^\S+@\S+\.\S+$/.test(v)) { emailError.value = '邮箱格式不正确'; return }
  debounce(async () => {
    try { const res = await auth.checkEmailAvailability(v); emailError.value = res.available ? null : '邮箱已被占用' }
    catch { emailError.value = '邮箱校验失败' }
  }, 400, 'email')
}

async function onLogin() {
  try {
    await store.login({ username: loginForm.username.trim(), password: loginForm.password })
    // 修复：登录成功后使用 replace，避免返回栈里仍有 /login
    router.replace(redirect.value || '/')
    // 清空表单，防止残留
    loginForm.username = ''; loginForm.password = ''
  } catch { /* 错误统一在 store.error 展示 */ }
}

async function onRegister() {
  clearRegisterErrors()
  if (!registerForm.password || registerForm.password.length < 8) { passwordError.value = '密码至少 8 位'; return }
  try {
    await store.register({
      username: registerForm.username.trim(),
      email: registerForm.email.trim(),
      password: registerForm.password,
    })
    router.replace(redirect.value || '/')
    registerForm.username = ''; registerForm.email = ''; registerForm.password = ''
  } catch { /* 错误统一在 store.error 展示 */ }
}

// 守卫：若已登录，自动跳转首页，避免登录页继续显示
watchEffect(() => {
  if (isAuthenticated.value) router.replace(redirect.value || '/')
})
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: var(--space-6);
  background: var(--bg);
  color: var(--text-primary);
}
.auth-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-2); padding: var(--space-6); width: 360px; max-width: 92vw; }
.auth-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-5); }
.brand { font-family: var(--font-sans); font-size: var(--text-xl); margin: 0; }
.theme-toggle { appearance: none; border: 1px solid var(--border); background: var(--surface-2); color: var(--text-secondary); border-radius: var(--radius-pill); padding: 6px 10px; cursor: pointer; transition: background var(--duration-medium) var(--ease); }
.theme-toggle:hover { background: var(--brand-weak); }
.tabs { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); margin-bottom: var(--space-4); }
.tab { border: 1px solid var(--border); background: var(--surface-2); color: var(--text-secondary); border-radius: var(--radius); padding: var(--space-3); cursor: pointer; }
.tab.active { border-color: var(--brand); color: var(--text-primary); box-shadow: var(--shadow-focus); }
.error { margin-bottom: var(--space-3); color: var(--danger); font-size: var(--text-sm); }
.el-reset :deep(.el-form-item) { margin-bottom: var(--space-3); }
.form .submit, .el-reset .submit { width: 100%; margin-top: var(--space-2); }
</style>