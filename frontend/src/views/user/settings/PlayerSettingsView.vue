<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { userSettings } from '@/api'
import type { PlayerSettings } from '@/types/user_settings'

const store = useUserStore()
const loading = ref(false)
const settings = ref<PlayerSettings | null>(null)

async function fetchSettings() {
  if (!store.token) return
  loading.value = true
  try {
    settings.value = await userSettings.getPlayerSettings(store.token)
  } catch {
    settings.value = null
  } finally {
    loading.value = false
  }
}

onMounted(fetchSettings)
</script>

<template>
  <div class="content player-settings-view">
    <section class="card section">
      <div class="section-header">
        <h3 class="section-title">播放设置</h3>
        <div class="section-meta text-muted">字幕、音轨、播放与默认模式</div>
      </div>

      <div class="grid two">
        <div class="card">
          <h4 class="sub-title">字幕模式</h4>
          <div class="row"><span class="label">自动加载字幕</span><span class="value">{{ settings?.auto_load_subtitle ? '是' : '否' }}</span></div>
          <div class="row"><span class="label">优先加载本地</span><span class="value">{{ settings?.prefer_local_subtitle ? '是' : '否' }}</span></div>
          <div class="row"><span class="label">在线检索字幕</span><span class="value">{{ settings?.online_subtitle_search ? '是' : '否' }}</span></div>
          <div class="row"><span class="label">默认字幕模式</span><span class="value">{{ settings?.subtitle_default_mode ?? '-' }}</span></div>
        </div>

        <div class="card">
          <h4 class="sub-title">音轨模式</h4>
          <div class="row"><span class="label">优先语言</span><span class="value">{{ settings?.audio_prefer_language ?? '-' }}</span></div>
          <div class="row"><span class="label">优先来源</span><span class="value">{{ settings?.audio_prefer_source ?? '-' }}</span></div>
          <div class="row"><span class="label">默认音轨模式</span><span class="value">{{ settings?.audio_default_mode ?? '-' }}</span></div>
        </div>
      </div>

      <div class="grid two">
        <div class="card">
          <h4 class="sub-title">播放模式</h4>
          <div class="row"><span class="label">倍速快捷步</span><span class="value">{{ settings?.speed_step ?? '-' }}</span></div>
          <div class="row"><span class="label">自动播放</span><span class="value">{{ settings?.auto_play ? '是' : '否' }}</span></div>
        </div>
        <div class="card">
          <h4 class="sub-title">最小界面模式</h4>
          <div class="row"><span class="label">最小界面上限</span><span class="value">{{ settings?.minimal_ui_max_level ?? '-' }}</span></div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.player-settings-view { padding-block: var(--space-5); }
.section { border-radius: var(--radius-lg); padding: var(--space-6); display: grid; gap: var(--space-5); box-shadow: var(--shadow-1); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.section-title { font-size: var(--text-lg); font-weight: 600; margin: 0; }
.sub-title { font-size: var(--text-md); font-weight: 600; margin: 0 0 var(--space-3); }

.grid.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--gap); }
.card { padding: var(--space-5); border-radius: var(--radius-md); box-shadow: var(--shadow-0); background: var(--surface-1); }
.row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) 0; }
.label { color: var(--text-secondary); }
.value { color: var(--text-primary); font-weight: 600; }

@media (max-width: 768px) {
  .grid.two { grid-template-columns: 1fr; }
}
</style>