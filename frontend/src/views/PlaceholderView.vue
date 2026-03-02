<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const title = computed(() => (route.meta?.title as string) || '列表页')
</script>

<template>
  <div class="page">
    <h2>{{ title }}</h2>
    <p>占位页面：后续替换为真实列表/网格。</p>
  </div>
</template>

<style scoped>
.page { padding: var(--space-6); color: var(--text-primary); }
</style>