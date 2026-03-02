<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useUserStore } from '@/stores/user'
import { users } from '@/api'

const store = useUserStore()

const avatarUrl = ref<string | null>(null)
const avatarError = ref(false)
const loadingAvatar = ref(false)
let abortCtrl: AbortController | null = null

const isAuthenticated = computed(() => store.isAuthenticated)
const displayName = computed(() => store.user?.username ?? '用户')
const initial = computed(() => (displayName.value?.[0] ?? '?').toUpperCase())

function goUser() {
  window.location.assign('http://localhost:15174/user')
}

async function fetchAvatar() {
  avatarError.value = false
  avatarUrl.value = null
  if (!store.token || !store.user?.id) return
  loadingAvatar.value = true
  try {
    if (abortCtrl) abortCtrl.abort()
    abortCtrl = new AbortController()
    const urls = await users.getUserProfilesSigned(store.token, [store.user.id], { signal: abortCtrl.signal })
    avatarUrl.value = urls?.[0] ?? null
  } catch {
    avatarUrl.value = null
  } finally {
    loadingAvatar.value = false
  }
}

watch(() => [store.token, store.user?.id], () => { fetchAvatar() })
onMounted(() => {
  fetchAvatar()
})
onBeforeUnmount(() => {
  if (abortCtrl) abortCtrl.abort()
})
</script>

<template>
  <div
    class="user-menu"
    role="button"
    @click="goUser"
  >
    <!-- Left: Avatar (32px, circle). Fallback to initial letter -->
    <div class="avatar" aria-hidden="true">
      <img v-if="isAuthenticated && avatarUrl && !avatarError" :src="avatarUrl" alt="" @error="avatarError = true" />
      <span v-else>{{ initial }}</span>
    </div>
    <!-- Middle: Username -->
    <div class="name" :title="displayName">{{ displayName }}</div>
    
  </div>
  
</template>

<style scoped>
.user-menu {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px 0 8px;
  border-radius: var(--radius-pill);
  background: color-mix(in oklab, var(--surface-2), white 18%);
  border: 1px solid color-mix(in oklab, var(--border), white 10%);
  color: color-mix(in oklab, var(--text-primary), var(--text-muted) 35%);
  cursor: pointer;
  transition: background var(--duration-medium) var(--ease),
              box-shadow var(--duration-medium) var(--ease),
              color var(--duration-medium) var(--ease);
}
.user-menu:hover { background: color-mix(in oklab, var(--surface-2), white 28%); box-shadow: var(--shadow-1); }
.user-menu:active { transform: translateY(1px); }

.avatar {
  width: 32px; height: 32px;
  border-radius: 50%;
  overflow: hidden;
  background: color-mix(in oklab, var(--surface-2), black 5%);
  display: grid; place-items: center;
  color: var(--text-secondary);
  font-weight: 700; font-size: var(--text-sm);
}
.avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }

.name {
  max-width: 140px;
  color: var(--text-primary);
  opacity: 0.9; /* 半透明灰（轻微） */
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-weight: 600; font-size: var(--text-sm);
}

@media (prefers-reduced-motion: reduce) {
  .user-menu { transition: none; }
}
</style>