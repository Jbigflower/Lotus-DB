<script setup lang="ts">
import { useRouter, RouterLink } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { useLayoutStore } from '@/stores/layout'
import UserMenu from '@/components/UserMenu.vue'

const router = useRouter()
const { isDark, toggleTheme } = useTheme()
const layout = useLayoutStore()

function toggleSidebar() { layout.toggleSidebar() }
function goSearch() { router.push('/search') }
function goLLM() { router.push('/llm') }
</script>

<template>
  <header class="app-header">
    <div class="left">
      <button class="btn btn--ghost btn--sm icon-btn" @click="toggleSidebar" title="侧栏" aria-label="切换侧栏">☰</button>
      <RouterLink class="brand" to="/">Lotus-DB</RouterLink>
      <nav class="main-nav">
        <RouterLink to="/libraries">媒体库</RouterLink>
        <RouterLink to="/favorites">最爱</RouterLink>
        <RouterLink to="/continue">继续看</RouterLink>
        <RouterLink to="/lists">片单</RouterLink>
      </nav>
    </div>

    <div class="right">
      <button
        class="btn btn--ghost btn--sm icon-btn theme-btn"
        @click="toggleTheme"
        :title="isDark ? '切换到日间' : '切换到夜间'"
        :aria-label="isDark ? '切换到日间主题' : '切换到夜间主题'"
        :aria-pressed="isDark"
      >
        <span v-if="isDark">🌙</span><span v-else>☀️</span>
      </button>
      <button class="btn btn--secondary btn--sm" @click="goLLM">LLM</button>
      <button class="btn btn--secondary btn--sm" @click="goSearch">检索</button>
      <UserMenu />
    </div>
  </header>
</template>

<style scoped>
.app-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--surface); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: var(--z-nav); backdrop-filter: saturate(120%) blur(6px); }
.left { display: flex; align-items: center; gap: 16px; }
.brand { font-weight: 600; color: var(--text-primary); text-decoration: none; }
.main-nav { display: flex; gap: 12px; }
.main-nav a { color: var(--text-secondary); text-decoration: none; padding: 6px 8px; border-radius: var(--radius); transition: background var(--duration-fast) var(--ease), color var(--duration-fast) var(--ease); }
.main-nav a.router-link-active { color: var(--text-primary); background: var(--surface-2); }
.main-nav a:hover { background: color-mix(in oklab, var(--surface-2), var(--brand-weak) 16%); color: var(--text-primary); }
.right { display: flex; align-items: center; gap: 8px; }
.icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; border-radius: var(--radius-pill); }
.theme-btn { line-height: 1; }
.left .btn--ghost { border: none; background: transparent; color: var(--text-secondary); border-radius: var(--radius); transition: background var(--duration-fast) var(--ease), color var(--duration-fast) var(--ease); }
.left .btn--ghost:hover { background: color-mix(in oklab, var(--surface-2), var(--brand-weak) 16%); color: var(--text-primary); }
.left .btn--ghost.btn--sm { padding: 0 8px; font-size: var(--text-sm); }
.left .icon-btn { border: none; background: transparent; color: var(--text-secondary); font-size: var(--text-sm); }
.left .icon-btn:hover { background: color-mix(in oklab, var(--surface-2), var(--brand-weak) 16%); color: var(--text-primary); }
</style>
