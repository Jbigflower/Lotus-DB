<template>
  <div class="llm-view">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <el-button class="new-chat-btn" @click="startNewChat">
          <el-icon class="mr-2"><Plus /></el-icon>
          <span>新对话</span>
        </el-button>
      </div>

      <div class="history-container" v-loading="loadingHistory">
        <div class="history-list">
          <div 
            v-for="th in threads" 
            :key="th.thread_id" 
            class="history-item"
            :class="{ active: currentThreadId === th.thread_id }"
            @click="chooseThread(th.thread_id)"
          >
            <div class="history-content">
              <div class="history-title" :title="th.preview || '无标题对话'">
                {{ th.preview || '无标题对话' }}
              </div>
              <div class="history-time">{{ formatDate(th.last_updated as any) }}</div>
            </div>
            <div class="history-actions">
               <el-popconfirm title="确定删除此对话吗？" @confirm="deleteChat(th.thread_id)" width="200">
                <template #reference>
                  <div class="action-btn delete" @click.stop>
                    <el-icon><Delete /></el-icon>
                  </div>
                </template>
              </el-popconfirm>
            </div>
          </div>
          
          <div v-if="threads.length === 0 && !loadingHistory" class="empty-history">
            <el-empty description="暂无历史对话" :image-size="60" />
          </div>
        </div>
      </div>
    </aside>

    <!-- 主聊天区域 -->
    <main class="chat-area">
      <div class="chat-header">
        <div class="header-info">
          <span class="header-title">{{ currentThreadTitle || '新对话' }}</span>
        </div>
        <div class="header-actions">
           <el-select 
             v-model="agentVersion" 
             placeholder="选择 Agent" 
             style="width: 160px"
             :disabled="!!currentThreadId"
             size="small"
           >
             <el-option label="React base" value="React base" />
             <el-option label="Plan base" value="Plan base" />
             <el-option label="Orchestrator base" value="Orchestrator base" />
             <el-option label="React Augment" value="React Augment" />
           </el-select>
           <el-button 
             size="small" 
             style="margin-left: 8px"
             :disabled="!langsmithEnabled"
             @click="openLangsmith"
           >
             LangSmith
           </el-button>
        </div>
      </div>

      <!-- 聊天内容 -->
      <div class="messages-container" ref="chatMainRef">
        <div v-if="messages.length === 0" class="welcome-screen">
          <div class="welcome-content">
            <div class="logo-wrapper">
              <span class="logo-emoji">🪷</span>
            </div>
            <h1 class="welcome-title">Lotus AI</h1>
            <p class="welcome-desc">您的个人智能助手，可以协助您管理媒体库、回答问题或进行创意写作。</p>
            
            <div class="suggestion-grid">
              <div class="suggestion-card" @click="quickAsk('帮我推荐几部科幻电影')">
                <div class="suggestion-icon">🎬</div>
                <div class="suggestion-text">推荐科幻电影</div>
              </div>
              <div class="suggestion-card" @click="quickAsk('如何添加新的媒体资源？')">
                <div class="suggestion-icon">📂</div>
                <div class="suggestion-text">添加媒体资源</div>
              </div>
              <div class="suggestion-card" @click="quickAsk('统计一下我的观影时长')">
                <div class="suggestion-icon">📊</div>
                <div class="suggestion-text">统计观影时长</div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="message-list">
          <div 
            v-for="(msg, index) in messages" 
            :key="index" 
            class="message-wrapper"
            :class="msg.role"
          >
            <div class="avatar-column">
              <div v-if="msg.role === 'assistant'" class="ai-avatar">
                <span class="avatar-emoji">🪷</span>
              </div>
              <el-avatar 
                v-else 
                :size="32" 
                :src="userAvatar" 
                class="user-avatar"
              >
                {{ userInitials }}
              </el-avatar>
            </div>
            
            <div class="content-column">
              <div class="message-bubble">
                <div v-if="msg.role === 'assistant'">
                  <div v-if="!msg.content" class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <div v-else class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
                </div>
                <div v-else class="user-text">{{ msg.content }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="input-container">
        <div class="input-wrapper">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 6 }"
            placeholder="给 Lotus 发送消息..."
            @keydown.enter.exact.prevent="sendMessage"
            class="chat-input"
            resize="none"
          />
          <el-button 
            class="send-btn"
            type="primary" 
            :icon="Position" 
            :disabled="!inputMessage.trim() || loading"
            @click="sendMessage"
            circle
          />
        </div>
        <div class="footer-note">
          内容由 AI 生成，请仔细甄别。
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, Position } from '@element-plus/icons-vue'
import { 
  chatStream,
  getThreads, 
  getThread,
  getLangsmithInfo,
  deleteThread,
  type ChatMessage, 
  type ThreadSummary 
} from '@/api/llm'
import { useUserStore } from '@/stores/user'
import { marked } from 'marked'

const userStore = useUserStore()
const messages = ref<ChatMessage[]>([])
const threads = ref<ThreadSummary[]>([])
const currentThreadId = ref<string>('')
const agentVersion = ref<string>('React base')
const inputMessage = ref('')
const loading = ref(false)
const loadingHistory = ref(false)
const chatMainRef = ref<HTMLElement | null>(null)
const langsmithEnabled = ref(false)
const langsmithUrl = ref('')
const threadStorageKey = 'llm_thread_id'

const openLangsmith = () => {
  if (langsmithUrl.value) {
    window.open(langsmithUrl.value, '_blank')
  }
}

const setThreadId = (id: string) => {
  currentThreadId.value = id
  if (id) {
    localStorage.setItem(threadStorageKey, id)
  } else {
    localStorage.removeItem(threadStorageKey)
  }
}

const getThreadId = () => {
  return currentThreadId.value || localStorage.getItem(threadStorageKey) || ''
}

// 用户信息
const userAvatar = computed(() => '')
const userInitials = computed(() => {
  const name = userStore.user?.username || 'User'
  return name.charAt(0).toUpperCase()
})

const currentThreadTitle = computed(() => {
  if (!currentThreadId.value) return ''
  const item = threads.value.find(c => c.thread_id === currentThreadId.value)
  return item?.preview || '无标题对话'
})

// Markdown 渲染
const renderMarkdown = (text: string) => {
  try {
    return marked.parse(text || '')
  } catch {
    return text
  }
}

// 格式化时间
const formatDate = (dateStr: string) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  
  if (days === 0) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } else if (days === 1) {
    return '昨天'
  } else if (days < 7) {
    return `${days}天前`
  } else {
    return date.toLocaleDateString([], { month: '2-digit', day: '2-digit' })
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (chatMainRef.value) {
    chatMainRef.value.scrollTop = chatMainRef.value.scrollHeight
  }
}

// 加载历史会话列表
const loadHistory = async () => {
  if (!userStore.token) return
  loadingHistory.value = true
  try {
    const res = await getThreads(userStore.token)
    threads.value = res
  } catch (error) {
    console.error('Load history failed', error)
  } finally {
    loadingHistory.value = false
  }
}

// 选择历史线程
const chooseThread = async (id: string) => {
  if (currentThreadId.value === id) return
  if (!userStore.token) return
  loading.value = true
  try {
    const detail = await getThread(userStore.token, id)
    setThreadId(detail.thread_id)
    messages.value = detail.messages || []
    scrollToBottom()
  } catch {
    ElMessage.error('加载会话失败')
  } finally {
    loading.value = false
  }
}

// 新建对话
const startNewChat = () => {
  setThreadId('')
  messages.value = []
  agentVersion.value = 'React base'
}

// 删除对话
const deleteChat = async (id: string) => {
  if (!userStore.token) return
  try {
    await deleteThread(userStore.token, id)
    threads.value = threads.value.filter(c => c.thread_id !== id)
    if (currentThreadId.value === id) {
      startNewChat()
    }
    ElMessage.success('删除成功')
  } catch {
    ElMessage.error('删除失败')
  }
}

const restoreThread = async () => {
  if (!userStore.token) return
  const storedId = localStorage.getItem(threadStorageKey)
  if (!storedId) return
  if (currentThreadId.value === storedId && messages.value.length > 0) return
  loading.value = true
  try {
    const detail = await getThread(userStore.token, storedId)
    setThreadId(detail.thread_id)
    messages.value = detail.messages || []
    scrollToBottom()
  } catch {
    setThreadId('')
  } finally {
    loading.value = false
  }
}

const quickAsk = (text: string) => {
  inputMessage.value = text
  sendMessage()
}

const sendMessage = async () => {
  const content = inputMessage.value.trim()
  if (!content) return
  if (!userStore.token) return
  
  const inheritedThreadId = getThreadId()
  if (inheritedThreadId && !currentThreadId.value) {
    setThreadId(inheritedThreadId)
  }
  
  // 乐观更新 UI
  messages.value.push({
    role: 'user',
    content: content
  })
  
  const tempInput = inputMessage.value
  inputMessage.value = ''
  loading.value = true
  scrollToBottom()
  
  // 添加空的 AI 回复占位
  messages.value.push({
    role: 'assistant',
    content: ''
  })
  const aiMessageRef = messages.value[messages.value.length - 1]
  
  try {
    const stream = chatStream(userStore.token, {
      query: content,
      thread_id: getThreadId() || undefined,
      agent_version: agentVersion.value
    })
    
    for await (const chunk of stream) {
      if (chunk.type === 'id') {
        setThreadId(chunk.content)
        loadHistory()
      } else if (chunk.type === 'text') {
        if (aiMessageRef) {
          aiMessageRef.content += chunk.content
          scrollToBottom()
        }
      } else if (chunk.type === 'status') {
        // Optional: display status (e.g. "Calling tool...")
        // We can append it temporarily or use a separate status field
        // For now, let's just log it or append as italic text
        // aiMessageRef.content += `\n*${chunk.content}*\n` 
      } else if (chunk.type === 'error') {
        if (aiMessageRef) {
          aiMessageRef.content += `\n**Error: ${chunk.content}**\n`
          scrollToBottom()
        }
      }
    }
    
    // 更新列表中的最后时间
    const idx = threads.value.findIndex(c => c.thread_id === currentThreadId.value)
    if (idx !== -1 && threads.value[idx]) {
      const now = new Date().toISOString()
      threads.value[idx].last_updated = now
      const item = threads.value.splice(idx, 1)[0]
      if (item) {
        threads.value.unshift(item)
      }
    }
    
  } catch (error: unknown) {
    console.error('Chat error:', error)
    const msg = error instanceof Error ? error.message : '发送失败，请重试'
    ElMessage.error(msg)
    // 恢复输入框
    inputMessage.value = tempInput
    // 移除 AI 消息和用户消息 (Find the message in the current array if it exists)
    if (aiMessageRef) {
        const msgIdx = messages.value.indexOf(aiMessageRef)
        if (msgIdx !== -1) {
            messages.value.splice(msgIdx, 1)
            // Check if previous is user message (it should be)
            const prevMsg = messages.value[msgIdx - 1]
            if (msgIdx > 0 && prevMsg && prevMsg.role === 'user' && prevMsg.content === content) {
                messages.value.splice(msgIdx - 1, 1)
            }
        }
    } else {
        // Fallback if array was replaced: we can't easily remove from new array
        // But if array was replaced, we probably shouldn't remove anything from the new conversation
    }
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

onMounted(() => {
  loadHistory()
  restoreThread()
  if (userStore.token) {
    getLangsmithInfo(userStore.token).then(info => {
      langsmithEnabled.value = info.enabled
      langsmithUrl.value = info.ui_url
    }).catch(() => {})
  }
})
</script>

<style scoped>
.llm-view {
  display: flex;
  height: 100%;
  width: 100%;
  background-color: #ffffff;
  position: relative;
  overflow: hidden;
}

/* Sidebar Styling */
.sidebar {
  width: 260px;
  background-color: #f9f9f9;
  border-right: 1px solid #e5e5e5;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 16px;
}

.new-chat-btn {
  width: 100%;
  justify-content: flex-start;
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid #e5e5e5;
  color: #333;
  transition: all 0.2s;
  background-color: #fff;
  font-weight: 500;
}

.new-chat-btn:hover {
  background-color: #f0f0f0;
  border-color: #dcdcdc;
  transform: translateY(-1px);
  box-shadow: 0 2px 5px rgba(0,0,0,0.05);
}

.history-container {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 10px;
}

.history-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  color: #333;
}

.history-item:hover {
  background-color: #eaeaea;
}

.history-item.active {
  background-color: #e6e6e6;
  font-weight: 500;
}

.history-content {
  flex: 1;
  overflow: hidden;
}

.history-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.history-time {
  font-size: 11px;
  color: #999;
}

.history-actions {
  opacity: 0;
  transition: opacity 0.2s;
}

.history-item:hover .history-actions {
  opacity: 1;
}

.action-btn {
  padding: 4px;
  border-radius: 4px;
  color: #666;
}

.action-btn:hover {
  background-color: #dcdcdc;
  color: #f56c6c;
}

/* Main Chat Area */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  background-color: #fff;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid #e5e5e5;
  background-color: #fff;
  flex-shrink: 0;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
  scroll-behavior: smooth;
}

.message-list {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 20px;
}

/* Welcome Screen */
.welcome-screen {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 0 20px;
  color: #333;
}

.welcome-content {
  max-width: 600px;
  text-align: center;
}

.logo-wrapper {
  margin-bottom: 24px;
}

.logo-emoji {
  font-size: 64px;
  display: block;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0% { transform: translateY(0px); }
  50% { transform: translateY(-10px); }
  100% { transform: translateY(0px); }
}

.welcome-title {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #2c3e50;
}

.welcome-desc {
  font-size: 16px;
  color: #666;
  margin-bottom: 40px;
  line-height: 1.5;
}

.suggestion-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  width: 100%;
}

.suggestion-card {
  background-color: #f9f9f9;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.suggestion-card:hover {
  background-color: #fff;
  border-color: #409EFF;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}

.suggestion-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.suggestion-text {
  font-size: 14px;
  color: #333;
  font-weight: 500;
}

/* Message Styling */
.message-wrapper {
  display: flex;
  margin-bottom: 32px;
  gap: 16px;
}

.message-wrapper.user {
  flex-direction: row-reverse;
}

.message-wrapper.user .content-column {
  display: flex;
  justify-content: flex-end;
}

.avatar-column {
  flex-shrink: 0;
  width: 32px;
  display: flex;
  justify-content: center;
}

.ai-avatar {
  width: 32px;
  height: 32px;
  background-color: #f0f0f0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e5e5e5;
}

.avatar-emoji {
  font-size: 18px;
}

.content-column {
  flex: 1;
  max-width: calc(100% - 96px);
}

.message-bubble {
  font-size: 16px;
  line-height: 1.6;
}

.user .message-bubble .user-text {
  background-color: #f4f4f4;
  padding: 10px 16px;
  border-radius: 16px;
  display: inline-block;
  color: #333;
}

.assistant .message-bubble {
  background-color: transparent;
  color: #2c3e50;
}

/* Markdown Styles */
.markdown-body :deep(p) {
  margin-bottom: 1em;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(pre) {
  background-color: #f6f8fa;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 1em 0;
}

.markdown-body :deep(code) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  background-color: rgba(175, 184, 193, 0.2);
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 85%;
}

.markdown-body :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 2em;
  margin-bottom: 1em;
}

/* Loading Animation */
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 0;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background-color: #ccc;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Input Area */
.input-container {
  padding: 24px 20px 32px;
  background: linear-gradient(180deg, rgba(255,255,255,0) 0%, #ffffff 20%);
}

.input-wrapper {
  max-width: 800px;
  margin: 0 auto;
  position: relative;
  background-color: #fff;
  border-radius: 16px;
  box-shadow: 0 0 15px rgba(0,0,0,0.1);
  border: 1px solid #e5e5e5;
  padding: 8px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.chat-input :deep(.el-textarea__inner) {
  box-shadow: none !important;
  border: none !important;
  background-color: transparent !important;
  padding: 8px 12px;
  font-size: 16px;
  line-height: 1.5;
}

.send-btn {
  margin-bottom: 2px;
  transition: all 0.2s;
}

.send-btn:not(:disabled):hover {
  transform: scale(1.05);
}

.footer-note {
  text-align: center;
  font-size: 12px;
  color: #999;
  margin-top: 12px;
}
</style>
