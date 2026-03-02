<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import LibraryCard from '@/components/ui/LibraryCard.vue'
import type { LibraryCardProps } from '@/components/ui/LibraryCard.vue'

const router = useRouter()

const libs = ref<LibraryCardProps[]>([
  { id: 'lib-001', name: '我的电影库', coverUrl: 'https://image.tmdb.org/t/p/w780/8QDQh3H3Z7Htv8SW0YBNNQ0pN22.jpg', mediaCount: 128, userName: 'Lotus', userAvatarUrl: 'https://i.pravatar.cc/80?img=5' },
  { id: 'lib-002', name: '欧美剧集', coverUrl: 'https://image.tmdb.org/t/p/w780/58GKcwFVgM8u4IBQjwVwFz6CWaI.jpg', mediaCount: 342, userName: 'Alice' },
  { id: 'lib-003', name: '动画片精选', coverUrl: 'https://image.tmdb.org/t/p/w780/t6HIqrRAclMCA60NsSmeqe9RmNV.jpg', mediaCount: 76, userName: 'Bob', userAvatarUrl: 'https://i.pravatar.cc/80?img=32' },
])

function openLibrary(id: string) {
  router.push(`/libraries/${id}`)
}
</script>

<template>
  <section class="content">
    <h2>LibraryCard 演示</h2>
    <p class="text-muted">竖向卡片，顶部封面，底部渐变遮罩显示库信息。</p>
    <div class="demo-grid">
      <LibraryCard v-for="l in libs" :key="l.id" v-bind="l" @open="openLibrary" />
    </div>
  </section>
  
</template>

<style scoped>
.demo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--gap);
  padding-block: var(--space-5);
}
</style>