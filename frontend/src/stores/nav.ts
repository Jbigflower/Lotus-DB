import { defineStore } from 'pinia'

export type NavItem = {
  id: string
  label: string
  to: string
  isPublic?: boolean
  ownerUserId?: string
  ownerUserName?: string
}

export type NavGroup = {
  id: string
  title: string
  items: NavItem[]
}

export const useNavStore = defineStore('nav', {
  state: () => ({
    groups: [
      {
        id: 'libraries',
        title: '媒体库',
        items: [
          { id: 'lib-movies', label: '电影库', to: '/libraries/movies', isPublic: true },
          { id: 'lib-shows', label: '剧集库', to: '/libraries/shows', isPublic: true },
          { id: 'lib-anime', label: '动漫库', to: '/libraries/anime' },
          { id: 'lib-doc', label: '纪录片', to: '/libraries/documentary' },
          { id: 'lib-music', label: '音乐库', to: '/libraries/music' },
        ],
      },
      {
        id: 'user',
        title: '用户',
        items: [
          { id: 'user-profile', label: '个人信息', to: '/user/profile' },
          { id: 'user-settings-display', label: '显示设置', to: '/user/settings/display' },
          { id: 'user-settings-player', label: '播放设置', to: '/user/settings/player' },
          { id: 'user-settings-notify', label: '通知设置', to: '/user/settings/notify' },
        ],
      },
      {
        id: 'services',
        title: '服务',
        items: [
          { id: 'search', label: '检索', to: '/search', isPublic: true },
          { id: 'semantic-search', label: '语义检索', to: '/search/semantic', isPublic: true },
          { id: 'llm', label: 'LLM', to: '/llm', isPublic: true },
          { id: 'tasks', label: '任务', to: '/tasks', isPublic: true },
          { id: 'recycle-bin', label: '回收站', to: '/recycle-bin', isPublic: true },
        ],
      },
      {
        id: 'admin',
        title: '管理',
        items: [
          { id: 'console', label: '控制台', to: '/admin/console' },
          { id: 'dashboard', label: '数据看板', to: '/admin/dashboard' },
          { id: 'users', label: '用户管理', to: '/admin/users' },
        ],
      },
    ] as NavGroup[],
  }),
  actions: {
    setGroups(groups: NavGroup[]) {
      this.groups = groups
    },
  },
})
