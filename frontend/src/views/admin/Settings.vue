<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import ListToolbar from '@/components/ui/ListToolbar.vue'
const { isDark, toggleTheme } = useTheme()
</script>

<template>
  <div class="admin-settings">
    <ListToolbar :viewMode="'list'" :disableViewToggle="true" />
    <section class="card">
      <header class="card__header"><h3>主题切换</h3></header>
      <div class="card__body">
        <button class="btn" @click="toggleTheme">切换为 {{ isDark ? '白天' : '黑夜' }}</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.admin-settings { padding: var(--space-6); display: grid; gap: var(--space-4); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); }
.card__header { display:flex; align-items:center; justify-content: space-between; padding: var(--space-4); border-bottom: 1px solid var(--border); }
.card__body { padding: var(--space-4); }
.btn { padding: 8px 12px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); }
</style>
