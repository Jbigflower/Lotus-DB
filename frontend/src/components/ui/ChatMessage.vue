<script setup lang="ts">
/**
 * 使用方式：
 * - 传入 role/content/variant/streaming/timestamp；
 * - 监听 @confirm/@feedback('up'|'down')；
 * - 开发模式下自动进行使用校验（useUsageCheck）。
 *
 * 设计思路：
 * - 气泡消息结构：头像+元信息+正文+动作；variant 控制不同态（normal/intermediate/result/confirmation）。
 * - 将校验逻辑封装为可复用钩子，避免生产环境影响。
 *
 * 页面表现（PlainText）：
 * - 左侧头像，右侧消息气泡；顶部显示角色/时间/流式状态；底部显示确认或反馈按钮（按 variant 决定）。
 */
import { useUsageCheck } from '../../composables/useUsageCheck'

defineOptions({ name: 'ChatMessage' })

export type ChatRole = 'user' | 'model'
export type ChatVariant = 'normal' | 'intermediate' | 'result' | 'confirmation'

export interface ChatMessageProps {
  role: ChatRole
  content: string
  variant?: ChatVariant
  streaming?: boolean
  timestamp?: string | Date
}

const props = defineProps<ChatMessageProps>()

useUsageCheck('ChatMessage', () => {
  const messages: Array<string | false> = []

  messages.push(!props.content?.trim() && 'content 为空：请传入有效文本')

  const modelOnly = props.variant === 'intermediate' || props.variant === 'result'
  messages.push(modelOnly && props.role !== 'model' && 'variant=intermediate/result 建议配合 role=model')

  messages.push(props.streaming && props.role !== 'model' && 'streaming 仅建议用于模型消息')

  if (props.timestamp && typeof props.timestamp === 'string') {
    const d = new Date(props.timestamp)
    messages.push(isNaN(d.getTime()) && 'timestamp 非法：请传入 Date 或 ISO 字符串')
  }

  return messages
})
const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'feedback', v: 'up' | 'down'): void
}>()
</script>

<template>
  <section class="chat-message" :data-role="props.role" :data-variant="props.variant ?? 'normal'">
    <aside class="avatar">{{ props.role === 'user' ? '👤' : '🤖' }}</aside>

    <div class="bubble">
      <header class="bubble__meta">
        <span class="role">{{ props.role === 'user' ? '用户' : '模型' }}</span>
        <time v-if="props.timestamp" class="time">{{ props.timestamp }}</time>
        <span v-if="props.streaming" class="streaming">…</span>
      </header>

      <article class="bubble__content">
        <!-- 可替换为 Markdown 渲染 -->
        <pre>{{ props.content }}</pre>
      </article>

      <footer class="bubble__actions">
        <slot name="actions" />
        <template v-if="props.variant === 'confirmation'">
          <button type="button" @click="emit('confirm')">确认</button>
        </template>
        <template v-if="props.variant === 'result' || props.variant === 'intermediate'">
          <button type="button" @click="emit('feedback', 'up')">👍</button>
          <button type="button" @click="emit('feedback', 'down')">👎</button>
        </template>
      </footer>
    </div>
  </section>
</template>