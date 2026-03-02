<script setup lang="ts">
const props = defineProps<{ name: string; size?: number }>()
const sz = props.size ?? 20
</script>

<template>
  <svg :width="sz" :height="sz" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <template v-if="name === 'play'">
      <polygon points="6 4 20 12 6 20 6 4" />
    </template>
    <template v-else-if="name === 'pause'">
      <line x1="6" y1="4" x2="6" y2="20" /><line x1="18" y1="4" x2="18" y2="20" />
    </template>
    <template v-else-if="name === 'fast-forward'">
      <polygon points="2 4 12 12 2 20 2 4" /><polygon points="12 4 22 12 12 20 12 4" />
    </template>
    <template v-else-if="name === 'rewind'">
      <polygon points="22 4 12 12 22 20 22 4" /><polygon points="12 4 2 12 12 20 12 4" />
    </template>
    <template v-else-if="name === 'volume-2'">
      <polygon points="11 5 6 9 3 9 3 15 6 15 11 19 11 5" />
      <path d="M15 9c1.5 1 2 2 2 3s-.5 2-2 3" />
      <path d="M18 7c2 1.5 3 3 3 5s-1 3.5-3 5" />
    </template>
    <template v-else-if="name === 'volume-x'">
      <polygon points="11 5 6 9 3 9 3 15 6 15 11 19 11 5" />
      <line x1="16" y1="9" x2="22" y2="15" /><line x1="22" y1="9" x2="16" y2="15" />
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a2 2 0 0 0 .2-1l2-2-2-2a2 2 0 0 0-.2-1l-2.2-.5-1.3-2-1 .1L12 4l-1 .1-1.3 2-2.2.5a2 2 0 0 0-.2 1L5 10l2 2a2 2 0 0 0 .2 1l2.2.5 1.3 2 1-.1L12 20l1-.1 1.3-2 2.2-.5Z" />
    </template>
    <template v-else-if="name === 'fullscreen'">
      <polyline points="3 9 3 3 9 3" /><polyline points="21 15 21 21 15 21" />
      <polyline points="15 3 21 3 21 9" /><polyline points="3 15 9 15 9 21" />
    </template>
    <template v-else-if="name === 'image-plus'">
      <rect x="3" y="5" width="14" height="12" rx="2" />
      <polyline points="4 15 8 11 10 13 13 10 16 13" />
      <line x1="20" y1="9" x2="20" y2="15" /><line x1="17" y1="12" x2="23" y2="12" />
    </template>
    <template v-else-if="name === 'image-play'">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <polygon points="10 10 15 12 10 14 10 10" />
    </template>
    <template v-else-if="name === 'bookmark-plus'">
      <path d="M6 4h12v16l-6-3-6 3V4z" />
      <line x1="12" y1="7" x2="12" y2="11" /><line x1="10" y1="9" x2="14" y2="9" />
    </template>
  </svg>
</template>

<style scoped>
svg { display: block }
</style>