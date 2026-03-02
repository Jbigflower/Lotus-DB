<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps<{
  src: string
  movieTitle?: string | null
  assetTitle?: string | null
  aspect?: '16:9' | '16:10' | '3:2' | '4:3' | '1:1'
}>()

const emit = defineEmits<{
  (e: 'ready', el: HTMLVideoElement): void
  (e: 'timeupdate', current: number, duration: number): void
  (e: 'state', playing: boolean): void
}>()

const container = ref<HTMLElement | null>(null)
const video = ref<HTMLVideoElement | null>(null)
const playing = ref(false)
const duration = ref(0)
const current = ref(0)

const ratio = computed(() => {
  const r = props.aspect ?? '16:9'
  const [w, h] = r.split(':').map(n => Number(n) || 1)
  return `${w} / ${h}`
})

function onTime() {
  const v = video.value
  if (!v) return
  current.value = v.currentTime
  duration.value = v.duration || 0
  emit('timeupdate', current.value, duration.value)
}
function onPlay() { playing.value = true; emit('state', true) }
function onPause() { playing.value = false; emit('state', false) }

onMounted(() => {
  const v = video.value
  if (v) emit('ready', v)
})

onBeforeUnmount(() => {})

watch(() => props.src, (s) => {
  const v = video.value
  if (v && s) {
    v.src = s
    v.load()
  }
})

 

async function snapshot(options?: { type?: string; quality?: number; width?: number; height?: number }): Promise<Blob> {
  const v = video.value
  if (!v) throw new Error('视频元素未就绪')
  const w0 = options?.width ?? v.videoWidth ?? v.clientWidth ?? 1
  const h0 = options?.height ?? v.videoHeight ?? v.clientHeight ?? 1
  const w = Math.max(1, Math.floor(Number(w0)))
  const h = Math.max(1, Math.floor(Number(h0)))
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d')
  if (!ctx) throw new Error('无法创建画布上下文')
  const css = getComputedStyle(v)
  const filter = css?.filter && css.filter !== 'none' ? css.filter : 'none'
  ctx.filter = filter
  ctx.drawImage(v, 0, 0, w, h)
  const type = options?.type ?? 'image/jpeg'
  const quality = options?.quality ?? 0.92
  const blob = await new Promise<Blob>((resolve, reject) => {
    c.toBlob((b) => { if (b) resolve(b); else reject(new Error('截图导出失败')) }, type, quality)
  })
  return blob
}

defineExpose({ container, snapshot })
</script>

<template>
  <div ref="container" class="player-shell">
    <div class="titlebar">
      <div class="titles">
        <span class="movie">{{ movieTitle ?? '' }}</span>
        <span v-if="assetTitle" class="sep">·</span>
        <span class="asset">{{ assetTitle ?? '' }}</span>
      </div>
    </div>
    <div class="stage" :style="{ aspectRatio: ratio }">
      <video
        ref="video"
        class="video"
        :src="src"
        crossorigin="anonymous"
        autoplay
        preload="metadata"
        @timeupdate="onTime"
        @play="onPlay"
        @pause="onPause"
      ></video>
      <div class="overlays">
        <slot name="progress"></slot>
        <slot name="controls"></slot>
        <slot name="side"></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-shell { display: grid; gap: var(--space-3); }
.titlebar { display: flex; justify-content: space-between; align-items: center; color: var(--text-secondary); }
.titles { display: inline-flex; gap: var(--space-2); align-items: baseline; }
.titles .movie { color: var(--text-primary); font-weight: 600; }
.titles .asset { color: var(--text-secondary); }
.titles .sep { color: var(--text-muted); }
.stage { position: relative; width: 100%; background: #000; border-radius: var(--radius); overflow: hidden; }
.video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; background: #000; }
.overlays { position: absolute; inset: 0; display: block; pointer-events: none; }
::v-deep(.overlay-layer) { pointer-events: auto; }
.overlays { z-index: var(--z-overlay); }

/* 全屏模式：让舞台填满视口，移除外层装饰 */
.player-shell:fullscreen { gap: 0; }
.player-shell:fullscreen .titlebar { display: none; }
.player-shell:fullscreen .stage { position: fixed; inset: 0; width: 100vw; height: 100vh; border-radius: 0; aspect-ratio: auto; }
.player-shell:fullscreen .overlays { position: fixed; inset: 0; }
</style>