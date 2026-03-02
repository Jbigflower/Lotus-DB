<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { userSettings } from '@/api'
import type { DisplaySettings } from '@/types/user_settings'

const store = useUserStore()
const loading = ref(false)
const settings = ref<DisplaySettings | null>(null)

async function fetchSettings() {
  if (!store.token) return
  loading.value = true
  try {
    settings.value = await userSettings.getDisplaySettings(store.token)
  } catch {
    settings.value = null
  } finally {
    loading.value = false
  }
}

onMounted(fetchSettings)
</script>

<template>
  <div class="content display-settings-view">
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">显示设置</h3>
        <div class="section-meta text-muted">语言、时区、主题、自定义样式</div>
      </div>

      <div class="grid two">
        <div class="card">
          <h4 class="sub-title">语言与时区</h4>
          <div class="row"><span class="label">语言</span><span class="value">{{ settings?.language ?? '-' }}</span></div>
          <div class="row"><span class="label">时区</span><span class="value">{{ settings?.timezone ?? '-' }}</span></div>
        </div>

        <div class="card">
          <h4 class="sub-title">主题</h4>
          <div class="row"><span class="label">主题</span><span class="value">{{ settings?.theme ?? '-' }}</span></div>
          <div class="row"><span class="label">分区大小</span><span class="value">{{ settings?.section_size ?? '-' }}</span></div>
        </div>
      </div>

      <div class="card">
        <h4 class="sub-title">自定义 CSS 片段</h4>
        <pre class="code" v-if="settings?.custom_css">{{ settings?.custom_css }}</pre>
        <p class="hint text-muted" v-else>暂无自定义样式。</p>
      </div>
    </section>
  </div>
</template>

<style scoped>
.display-settings-view { padding-block: var(--space-5); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.section-title { font-size: var(--text-lg); font-weight: 600; margin: 0; }
.sub-title { font-size: var(--text-md); font-weight: 600; margin: 0 0 var(--space-3); }

.grid.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }
.card { padding: var(--space-5); border-radius: var(--radius-md); box-shadow: var(--shadow-0); background: var(--surface-1); }
.row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; }
.label { color: var(--text-secondary); }
.value { color: var(--text-primary); font-weight: 600; }
.code { background: var(--surface-2); border-radius: var(--radius-md); padding: var(--space-4); overflow: auto; }
.hint { margin-top: var(--space-2); }

@media (max-width: 768px) {
  .grid.two { grid-template-columns: 1fr; }
}
</style>