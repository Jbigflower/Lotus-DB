<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { useNavStore, type NavGroup } from '@/stores/nav'
import { useUserStore } from '@/stores/user'
import { UserRole } from '@/types/user'
import { listLibraries } from '@/api/libraries'
import { users } from '@/api'
import { LibraryType } from '@/types/library'

const nav = useNavStore()
const userStore = useUserStore()

const canManage = computed(() => (userStore.user?.role ?? UserRole.GUEST) === UserRole.ADMIN)
const groups = computed<NavGroup[]>(() => nav.groups.filter(g => g.id !== 'admin' ? true : canManage.value))

const openGroups = ref<Record<string, boolean>>({})
function isOpen(id: string) { return openGroups.value[id] ?? true }
function toggle(id: string) { openGroups.value[id] = !isOpen(id) }

// ResizeObserver：为每个分组的内容容器动态记录高度，优化折叠动画与布局
const itemRefs = new Map<string, HTMLElement>()
const observers = new Map<string, ResizeObserver>()
function setItemRef(id: string, el: HTMLElement | null) {
  // 清理旧 observer
  const old = observers.get(id)
  if (old) { old.disconnect(); observers.delete(id) }

  if (!el) { itemRefs.delete(id); return }
  itemRefs.set(id, el)

  // 初始化变量并创建观察器
  el.style.setProperty('--group-height', `${el.scrollHeight}px`)
  const ro = new ResizeObserver(entries => {
    for (const e of entries) {
      const h = Math.ceil(e.contentRect.height)
      // 使用内容区高度或 scrollHeight，避免折叠时残留空白
      el.style.setProperty('--group-height', `${Math.max(h, el.scrollHeight)}px`)
    }
  })
  ro.observe(el)
  observers.set(id, ro)
}

onBeforeUnmount(() => { observers.forEach(o => o.disconnect()); observers.clear() })

async function loadLibraries() {
  if (!userStore.token) return
  const token = userStore.token
  const resMovie = await listLibraries(token, { library_type: LibraryType.MOVIE, page_size: 50 })
  const resTv = await listLibraries(token, { library_type: LibraryType.TV, page_size: 50 })
  const libs = [...resMovie.items, ...resTv.items]
  const items = libs.map(l => ({
    id: l.id,
    label: l.name,
    to: `/libraries/${l.id}`,
    isPublic: l.is_public,
    ownerUserId: l.user_id,
  }))
  const ownerIds = Array.from(new Set(items.map(i => i.ownerUserId).filter(Boolean))) as string[]
  const selfId = userStore.user?.id
  const queryIds = ownerIds.filter(id => id !== selfId)
  if (token && queryIds.length) {
    try {
      const mapping = await users.getUserMapping(token, queryIds)
      items.forEach(i => { if (i.ownerUserId && i.ownerUserId !== selfId) i.ownerUserName = mapping[i.ownerUserId] })
    } catch {}
  }
  const nextGroups: NavGroup[] = nav.groups.map(g => (
    g.id === 'libraries' ? { ...g, items } : g
  ))
  nav.setGroups(nextGroups)
}

onMounted(() => { loadLibraries() })
</script>

<template>
  <aside class="sidebar-nav">
    <!-- 返回按钮已迁移至 Header -->
    <div v-for="g in groups" :key="g.id" class="group">
      <div class="group-header" @click="toggle(g.id)">
        <span class="title">{{ g.title }}</span>
        <span class="chev" :class="{ open: isOpen(g.id) }">▾</span>
      </div>
      <Transition name="collapse">
        <ul 
          v-if="isOpen(g.id)" 
          class="items"
          :ref="(el) => setItemRef(g.id, el as HTMLElement)"
        >
          <li v-for="item in g.items" :key="item.id">
            <RouterLink :to="item.to">
              <span class="label">{{ item.label }}</span>
              <span v-if="item.isPublic" class="badge">公共</span>
              <span v-if="item.ownerUserId && item.ownerUserId !== userStore.user?.id" class="badge">{{ item.ownerUserName ?? '所属用户' }}</span>
            </RouterLink>
          </li>
        </ul>
      </Transition>
    </div>
  </aside>
</template>

<style scoped>
.sidebar-nav { display: flex; flex-direction: column; gap: 12px; padding: 12px; background: var(--surface); height: 100%; overflow: auto; }
.group { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-1); overflow: hidden; }
.group-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; cursor: pointer; color: var(--text-primary); }
.items { list-style: none; margin: 0; padding: 6px 10px 10px; display: grid; gap: 6px; overflow: hidden; }
.items a { display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); text-decoration: none; padding: 4px 6px; border-radius: var(--radius); }
.items a.router-link-active { color: var(--text-primary); background: var(--surface-2); }
.badge { font-size: var(--text-xs); color: var(--brand); border: 1px solid var(--brand); border-radius: var(--radius-pill); padding: 0 6px; }
.chev { transform: rotate(-90deg); transition: transform 0.2s ease; }
.chev.open { transform: rotate(0deg); }
/* 优化折叠动画 */
.collapse-enter-active, .collapse-leave-active {
  transition: max-height 0.2s ease, opacity 0.2s ease;
  overflow: hidden; /* 确保内容超出时隐藏 */
}
.collapse-enter-from, .collapse-leave-to {
  max-height: 0;
  opacity: 0;
}
/* 移除固定max-height，使用元素自身高度 */
.collapse-enter-to, .collapse-leave-from {
  max-height: var(--group-height); /* 动态变量 */
  opacity: 1;
}

/* 为每个分组添加动态高度变量 */
.items {
  --group-height: auto; /* 默认值 */
}
</style>
