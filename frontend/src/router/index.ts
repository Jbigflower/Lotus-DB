import { createRouter, createWebHistory } from 'vue-router'
import { setAuthErrorHandler } from '@/api/http'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    // 修正：使用现有 Home.vue
    { path: '/', name: 'home', component: () => import('@/views/Home.vue') },
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    // 新增：全局入口与用户相关列表的最小占位
    { path: '/search', name: 'search', component: () => import('@/views/SearchView.vue') },
    { path: '/search/semantic', name: 'semantic-search', meta: { title: '语义检索' }, component: () => import('@/views/SemanticSearchView.vue') },
    { path: '/llm', name: 'llm', component: () => import('@/views/LlmView.vue') },
    { path: '/recycle-bin', name: 'recycle-bin', meta: { title: '回收站' }, component: () => import('@/views/admin/RecycleBin.vue') },
    { path: '/user', name: 'user', component: () => import('@/views/UserView.vue') },
    // 用户详情子页：个人信息与设置
    { path: '/user/profile', name: 'user-profile', meta: { title: '个人信息' }, component: () => import('@/views/user/ProfileView.vue') },
    { path: '/user/settings/display', name: 'user-settings-display', meta: { title: '显示设置' }, component: () => import('@/views/user/settings/DisplaySettingsView.vue') },
    { path: '/user/settings/player', name: 'user-settings-player', meta: { title: '播放设置' }, component: () => import('@/views/user/settings/PlayerSettingsView.vue') },
    { path: '/user/settings/notify', name: 'user-settings-notify', meta: { title: '通知设置' }, component: () => import('@/views/user/settings/NotifySettingsView.vue') },

    // 用户分组页面
    { path: '/favorites', name: 'favorites', meta: { title: '收藏夹' }, component: () => import('@/views/user/FavoritesView.vue') },
    { path: '/continue', name: 'continue', meta: { title: '继续观看' }, component: () => import('@/views/user/ContinueWatchingView.vue') },
    { path: '/watch-later', name: 'watch-later', meta: { title: '稍后看' }, component: () => import('@/views/user/WatchLaterView.vue') },
    { path: '/lists', name: 'lists', meta: { title: '用户片单' }, component: () => import('@/views/user/UserCollectionsView.vue') },
    { path: '/lists/:id', name: 'list-detail', meta: { title: '片单详情' }, component: () => import('@/views/user/PlaylistDetailView.vue') },
    { path: '/recent', name: 'recent', meta: { title: '最近添加' }, component: () => import('@/views/recent/RecentAddedView.vue') },

    // 媒体库（占位）
    { path: '/libraries', name: 'libraries', meta: { title: '我的媒体库' }, component: () => import('@/views/library/LibraryListView.vue') },
    { path: '/libraries/:id', name: 'library', meta: { title: '媒体库详情' }, component: () => import('@/views/library/LibraryDetailView.vue') },
    // 电影详情页
    { path: '/movies/:id', name: 'movie', meta: { title: '电影详情' }, component: () => import('@/views/movie/MovieDetailView.vue') },
    // 播放器
    { path: '/player/:id', name: 'player', meta: { title: '播放器' }, component: () => import('@/views/player/MoviePlayerView.vue') },
    // 管理员页面
    { path: '/admin/console', name: 'admin-console', meta: { title: '控制台', requiresAdmin: true }, component: () => import('@/views/admin/ConsoleView.vue') },
    { path: '/admin/dashboard', name: 'admin-dashboard', meta: { title: '数据总览', requiresAdmin: true }, component: () => import('@/views/admin/DashboardView.vue') },
    { path: '/admin/users', name: 'admin-users', meta: { title: '用户管理', requiresAdmin: true }, component: () => import('@/views/admin/Users.vue') },
    { path: '/admin/settings', name: 'admin-settings', meta: { title: '系统设置', requiresAdmin: true }, component: () => import('@/views/admin/Settings.vue') },

    // 公共服务页面
    { path: '/tasks', name: 'tasks', meta: { title: '后台任务' }, component: () => import('@/views/admin/Tasks.vue') },

    // Demo: MediaCard
    { path: '/demo/media-card', name: 'demo-media-card', component: () => import('@/views/demo/MediaCardDemo.vue') },

    // Demo: LibraryCard
    { path: '/demo/library-card', name: 'demo-library-card', component: () => import('@/views/demo/LibraryCardDemo.vue') },

    // Demo: MediaGrid
    { path: '/demo/media-grid', name: 'demo-media-grid', component: () => import('@/views/demo/MediaGridDemo.vue') },

    
  ],
})
// 登录守卫：已登录用户访问 /login 自动回首页
import { useUserStore } from '@/stores/user'
import { UserRole } from '@/types/user'
router.beforeEach((to, _from, next) => {
  const store = useUserStore()
  if (to.path === '/login' && store.isAuthenticated) return next('/')
  // 管理员守卫
  if (to.path.startsWith('/admin')) {
    if (!store.isAuthenticated) return next('/login')
    const isAdmin = store.hasRole?.(UserRole.ADMIN)
    if (!isAdmin) return next('/')
  }
  next()
})

// 统一处理 401：清理登录状态并跳转到登录页，带上来源页作为 redirect
setAuthErrorHandler(() => {
  const store = useUserStore()
  const current = router.currentRoute.value
  const redirect = current?.fullPath && current.fullPath !== '/login'
    ? `?redirect=${encodeURIComponent(current.fullPath)}`
    : ''
  store.logout().catch(() => {})
  if (current?.path !== '/login') router.replace(`/login${redirect}`)
})

export default router
