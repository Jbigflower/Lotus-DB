<script setup lang="ts">
import { ref, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { semanticSearch } from '@/api/search'
import type { SemanticSearchParams, SemanticSearchResult } from '@/types/search'
import type { MovieRead } from '@/types/movie'
import MediaCard from '@/components/ui/MediaCard.vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()

const query = ref('')
const loading = ref(false)
const results = ref<SemanticSearchResult | null>(null)

// Filters
const searchTypes = ref<string[]>(['movies', 'notes', 'subtitles'])
const availableTypes = [
  { value: 'movies', label: '影视' },
  { value: 'notes', label: '笔记' },
  { value: 'subtitles', label: '字幕' },
]

// Advanced Options
const showAdvanced = ref(false)
const topK = ref(20)
const vectorWeight = ref(0.7)
const keywordWeight = ref(0.3)
const useCache = ref(true)

const doSearch = async () => {
  if (!query.value.trim()) {
    ElMessage.warning('请输入搜索内容')
    return
  }
  loading.value = true
  results.value = null
  try {
    const params: SemanticSearchParams = {
      query: query.value,
      types: searchTypes.value,
      top_k: topK.value,
      vector_weight: vectorWeight.value,
      keyword_weight: keywordWeight.value,
      use_cache: useCache.value,
      size: 50,
    }
    if (!userStore.token) {
        ElMessage.error('请先登录')
        return
    }
    const res = await semanticSearch(userStore.token, params)
    results.value = res
  } catch (e) {
    console.error(e)
    ElMessage.error('搜索失败')
  } finally {
    loading.value = false
  }
}

const goToMovie = (id: string) => router.push(`/movies/${id}`)
const playAt = (movieId: string, time: number) => router.push(`/player/${movieId}?t=${Math.floor(time)}`)

const formatTime = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h > 0 ? h + ':' : ''}${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

const formatScore = (score: number) => (score * 100).toFixed(1)

const getPosterUrl = (movie: MovieRead) => {
  if (movie.has_poster) {
    return `/api/v1/movies/${movie.id}/poster`
  }
  return undefined
}

const getYear = (movie: MovieRead) => {
  if (typeof movie.release_date === 'string') {
    const parts = movie.release_date.split('-')
    return parts[0] ? parseInt(parts[0]) : undefined
  }
  return undefined
}

// Computed results
const hasResults = computed(() => results.value !== null)
const movies = computed(() => (results.value?.data.movies?.items || [])
  .map(item => item.movie)
  .filter((m): m is MovieRead => !!m)
)
const notes = computed(() => (results.value?.data.notes?.items || []).map(item => ({
  ...item,
  chunk: item.chunk as unknown as { content: string },
  movie: item.movie as unknown as { id: string; title: string; title_cn: string }
})))
const subtitles = computed(() => (results.value?.data.subtitles?.items || []).map(item => ({
  ...item,
  chunk: item.chunk as unknown as { content: string; start_time: number; end_time: number },
  movie: item.movie as unknown as { id: string; title: string; title_cn: string }
})))

const activeTab = ref('all')
const tabs = computed(() => {
  const t = [{ id: 'all', label: '全部' }]
  if (movies.value.length) t.push({ id: 'movies', label: `影视 (${movies.value.length})` })
  if (notes.value.length) t.push({ id: 'notes', label: `笔记 (${notes.value.length})` })
  if (subtitles.value.length) t.push({ id: 'subtitles', label: `字幕 (${subtitles.value.length})` })
  return t
})

</script>

<template>
  <div class="semantic-search-view page-container">
    <header class="search-header">
      <h1 class="page-title">语义检索</h1>
      <div class="search-box">
        <input 
          v-model="query" 
          @keyup.enter="doSearch"
          type="text" 
          placeholder="输入描述性语句，如 '适合雨天看的治愈电影'..." 
          class="search-input"
        />
        <button class="search-btn" @click="doSearch" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          <span v-else>搜索</span>
        </button>
      </div>
      
      <div class="search-options">
        <div class="types-group">
          <label v-for="t in availableTypes" :key="t.value" class="checkbox-label">
            <input type="checkbox" :value="t.value" v-model="searchTypes">
            {{ t.label }}
          </label>
        </div>
        <button class="toggle-advanced" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '收起高级选项' : '高级选项' }}
        </button>
      </div>

      <div v-if="showAdvanced" class="advanced-panel">
        <div class="option-row">
          <label>向量权重 ({{ vectorWeight }})</label>
          <input type="range" min="0" max="1" step="0.1" v-model.number="vectorWeight">
        </div>
        <div class="option-row">
          <label>关键词权重 ({{ keywordWeight }})</label>
          <input type="range" min="0" max="1" step="0.1" v-model.number="keywordWeight">
        </div>
        <div class="option-row">
          <label>召回数量 ({{ topK }})</label>
          <input type="number" min="1" max="100" v-model.number="topK" class="number-input">
        </div>
        <div class="option-row">
          <label>
            <input type="checkbox" v-model="useCache"> 启用缓存
          </label>
        </div>
      </div>
    </header>

    <main v-if="hasResults" class="search-results">
      <div class="tabs">
        <button 
          v-for="tab in tabs" 
          :key="tab.id"
          :class="['tab-btn', { active: activeTab === tab.id }]"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="results-content">
        <!-- Movies -->
        <section v-if="(activeTab === 'all' || activeTab === 'movies') && movies.length" class="result-section">
          <h2 class="section-title" v-if="activeTab === 'all'">影视结果</h2>
          <div class="media-grid">
            <MediaCard 
              v-for="m in movies" 
              :key="m.id" 
              :id="m.id" 
              :title="m.title_cn || m.title"
              :poster="getPosterUrl(m)"
              :year="getYear(m)"
              :rating="m.rating || undefined"
              @open="goToMovie(m.id)"
              @play="goToMovie(m.id)"
            />
          </div>
        </section>

        <!-- Notes -->
        <section v-if="(activeTab === 'all' || activeTab === 'notes') && notes.length" class="result-section">
          <h2 class="section-title" v-if="activeTab === 'all'">笔记结果</h2>
          <div class="list-grid">
            <div v-for="(item, idx) in notes" :key="idx" class="result-card note-card">
              <div class="card-header">
                <span class="badge note-badge">笔记</span>
                <span class="score" title="综合匹配度">{{ formatScore(item.score) }}%</span>
              </div>
              <div class="card-body">
                <p class="content-text">{{ item.chunk.content }}</p>
              </div>
              <div class="card-footer" @click="goToMovie(item.movie.id)">
                <span class="source-movie">《{{ item.movie.title_cn || item.movie.title }}》</span>
                <span class="arrow">→</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Subtitles -->
        <section v-if="(activeTab === 'all' || activeTab === 'subtitles') && subtitles.length" class="result-section">
          <h2 class="section-title" v-if="activeTab === 'all'">字幕结果</h2>
          <div class="list-grid">
            <div v-for="(item, idx) in subtitles" :key="idx" class="result-card subtitle-card">
              <div class="card-header">
                <span class="badge subtitle-badge">字幕</span>
                <span class="time-range">{{ formatTime(item.chunk.start_time) }} - {{ formatTime(item.chunk.end_time) }}</span>
                <span class="score">{{ formatScore(item.score) }}%</span>
              </div>
              <div class="card-body">
                <p class="content-text">{{ item.chunk.content }}</p>
              </div>
              <div class="card-footer actions">
                <span class="source-movie" @click="goToMovie(item.movie.id)">《{{ item.movie.title_cn || item.movie.title }}》</span>
                <button class="play-btn" @click="playAt(item.movie.id, item.chunk.start_time)">
                  ▶ 跳转播放
                </button>
              </div>
            </div>
          </div>
        </section>

        <div v-if="!movies.length && !notes.length && !subtitles.length" class="no-results">
          未找到相关结果
        </div>
      </div>
    </main>

    <div v-else-if="loading" class="loading-state">
      <div class="spinner large"></div>
      <p>正在进行语义分析与检索...</p>
    </div>
    
    <div v-else class="empty-state">
      <div class="icon">🔍</div>
      <p>尝试搜索剧情、台词或笔记内容</p>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
  color: var(--color-text-primary);
}

.search-header {
  margin-bottom: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.page-title {
  font-size: 1.8rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.search-box {
  display: flex;
  gap: 1rem;
}

.search-input {
  flex: 1;
  padding: 1rem 1.5rem;
  font-size: 1.1rem;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  transition: all 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px rgba(var(--color-primary-rgb), 0.2);
}

.search-btn {
  padding: 0 2rem;
  font-size: 1.1rem;
  font-weight: 500;
  border-radius: 8px;
  background: var(--color-primary);
  color: white;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
  min-width: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.search-btn:hover {
  filter: brightness(1.1);
}

.search-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.search-options {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.types-group {
  display: flex;
  gap: 1.5rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}

.toggle-advanced {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 0.9rem;
}

.toggle-advanced:hover {
  color: var(--color-primary);
}

.advanced-panel {
  background: var(--color-bg-secondary);
  padding: 1.5rem;
  border-radius: 8px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-top: 0.5rem;
}

.option-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.option-row label {
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}

.number-input {
  padding: 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

/* Tabs */
.tabs {
  display: flex;
  gap: 1rem;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 1.5rem;
}

.tab-btn {
  padding: 0.75rem 1.5rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 1rem;
  transition: all 0.2s;
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.tab-btn:hover:not(.active) {
  color: var(--color-text-primary);
}

/* Results */
.result-section {
  margin-bottom: 3rem;
}

.section-title {
  font-size: 1.2rem;
  margin-bottom: 1rem;
  padding-left: 0.5rem;
  border-left: 4px solid var(--color-primary);
}

.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1.5rem;
}

.list-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.result-card {
  background: var(--color-bg-secondary);
  border-radius: 8px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  transition: transform 0.2s, box-shadow 0.2s;
  border: 1px solid transparent;
}

.result-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  border-color: var(--color-border-hover);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.85rem;
}

.badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
}

.note-badge {
  background: rgba(var(--color-yellow-rgb), 0.2);
  color: var(--color-yellow);
}

.subtitle-badge {
  background: rgba(var(--color-blue-rgb), 0.2);
  color: var(--color-blue);
}

.score {
  color: var(--color-green);
  font-weight: bold;
}

.content-text {
  font-size: 0.95rem;
  line-height: 1.5;
  color: var(--color-text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  margin-top: auto;
  padding-top: 0.8rem;
  border-top: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.card-footer:hover .source-movie {
  color: var(--color-primary);
}

.actions {
  cursor: default;
}

.source-movie {
  cursor: pointer;
  font-weight: 500;
}

.play-btn {
  background: var(--color-primary);
  color: white;
  border: none;
  padding: 0.3rem 0.8rem;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
}

.play-btn:hover {
  filter: brightness(1.1);
}

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 0;
  color: var(--color-text-secondary);
  gap: 1rem;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid rgba(255,255,255,0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 1s ease-in-out infinite;
}

.spinner.large {
  width: 48px;
  height: 48px;
  border-color: var(--color-border);
  border-top-color: var(--color-primary);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.icon {
  font-size: 3rem;
  opacity: 0.5;
}
</style>
