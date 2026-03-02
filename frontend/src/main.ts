import './styles/index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

// 提前初始化主题，避免加载初期的亮/暗闪烁
(() => {
  try {
    const key = 'lotusdb.theme'
    const saved = typeof window !== 'undefined' ? localStorage.getItem(key) : null
    const sysDark = typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    const initial = saved === 'dark' ? 'dark' : saved === 'light' ? 'light' : (sysDark ? 'dark' : 'light')
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', initial)
    }
  } catch {}
})()


const app = createApp(App)
app.use(ElementPlus)
app.use(createPinia())
app.use(router)

app.mount('#app')
