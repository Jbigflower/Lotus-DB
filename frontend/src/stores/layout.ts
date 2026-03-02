import { defineStore } from 'pinia'

export const useLayoutStore = defineStore('layout', {
  state: () => ({
    sidebarVisible: true,
  }),
  actions: {
    toggleSidebar() {
      this.sidebarVisible = !this.sidebarVisible
    },
    showSidebar() {
      this.sidebarVisible = true
    },
    hideSidebar() {
      this.sidebarVisible = false
    },
  },
})