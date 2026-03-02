<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import SidebarNav from '@/components/SidebarNav.vue'
import { useLayoutStore } from '@/stores/layout'
import { computed } from 'vue'

const route = useRoute()
const isFullScreen = computed(() => ['llm', 'player'].includes(route.name as string))
</script>

<template>
  <!-- 全局布局：顶部栏 + 侧边栏 + 主区域 -->
  <div class="layout">
    <AppHeader />
    <div class="app-content">
      <aside class="sidebar" :class="{ collapsed: !useLayoutStore().sidebarVisible }">
        <SidebarNav />
      </aside>
      <main class="main" :class="{ 'no-padding': isFullScreen }">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
header {
  line-height: 1.5;
  max-height: 100vh;
}

.logo {
  display: block;
  margin: 0 auto 2rem;
}

nav {
  width: 100%;
  font-size: 12px;
  text-align: center;
  margin-top: 2rem;
}

nav a.router-link-exact-active {
  color: var(--brand);
}

nav a.router-link-exact-active:hover {
  background-color: transparent;
}

nav a {
  display: inline-block;
  padding: 0 1rem;
  border-left: 1px solid var(--border);
}

nav a:first-of-type {
  border: 0;
}

@media (min-width: 1024px) {
  header {
    display: flex;
    place-items: center;
    padding-right: calc(var(--section-gap) / 2);
  }

  .logo {
    margin: 0 2rem 0 0;
  }

  header .wrapper {
    display: flex;
    place-items: flex-start;
    flex-wrap: wrap;
  }

  nav {
    text-align: left;
    margin-left: -1rem;
    font-size: 1rem;

    padding: 1rem 0;
    margin-top: 1rem;
  }
}
.layout {
  min-height: 100vh;
  background: var(--bg);
  color: var(--text-primary);
  display: grid;
  grid-template-rows: auto 1fr;
}
.app-content {
  display: flex;
}
.sidebar {
  position: fixed;
  top: var(--header-height);
  left: 0;
  height: calc(100vh - var(--header-height));
  width: 260px;
  border-right: 1px solid var(--border);
  background: var(--surface);
  overflow: hidden;
  transition: width 0.25s ease, border-color 0.25s ease;
}
.sidebar.collapsed {
  width: 0;
  border-right-color: transparent;
}
.sidebar.collapsed + .main {
  margin-left: 0;
}
.main {
  margin-left: 260px;
  padding: var(--space-6);
  flex: 1;
  overflow-y: auto;
}
.main.no-padding {
  padding: 0;
  overflow: hidden; /* 防止出现双重滚动条，由内部组件处理滚动 */
}
@media (max-width: 768px) {
  .app-content {
    flex-direction: column;
  }
  .sidebar {
    display: none;
  }
  .main {
    margin-left: 0;
  }
}
.layout:fullscreen .app-header { display: none; }
.layout:fullscreen .sidebar { display: none; }
.layout:fullscreen .main { margin-left: 0; padding: 0; }
</style>
