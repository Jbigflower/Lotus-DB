import { ref, computed, onMounted } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_THEME_KEY = 'lotusdb.theme'

function applyThemeToDOM(theme: Theme) {
  const html = document.documentElement
  html.setAttribute('data-theme', theme)
}

function getStoredTheme(): Theme | null {
  if (typeof window === 'undefined') return null
  const v = localStorage.getItem(STORAGE_THEME_KEY)
  return v === 'dark' ? 'dark' : v === 'light' ? 'light' : null
}

function getSystemTheme(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
  const theme = ref<Theme>('light')
  const isDark = computed(() => theme.value === 'dark')

  function setTheme(t: Theme, persist = true) {
    theme.value = t
    if (persist && typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_THEME_KEY, t)
    }
    applyThemeToDOM(t)
  }

  function toggleTheme() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark')
  }

  function initTheme() {
    const saved = getStoredTheme()
    setTheme(saved ?? getSystemTheme(), false)
  }

  onMounted(() => {
    initTheme()
  })

  return { theme, isDark, setTheme, toggleTheme, initTheme }
}