import { http, resolveBaseURL } from '@/api/http'

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  created_at?: string
}

export interface AgentConfig {
  model: string
  provider: string
  system_prompt_version?: string
  agent_version?: string
}

export interface ThreadSummary {
  thread_id: string
  last_updated?: string
  preview?: string
}

export interface ThreadDetail {
  thread_id: string
  messages: ChatMessage[]
  last_updated?: string
  preview?: string
}

export interface ChatRequest {
  query: string
  thread_id?: string
  agent_version?: string
}

export interface ChatResponse {
  final_response: string
  thread_id: string
}

export interface StreamChunk {
  type: 'id' | 'text' | 'status' | 'error'
  content: string
}

export function chatWithAgent(token: string, data: ChatRequest) {
  return http.post<ChatResponse>('/api/v1/llm/chat', data, { token })
}

export function getThreads(token: string) {
  return http.get<ThreadSummary[]>('/api/v1/llm/threads', { token })
}

export function getThread(token: string, id: string) {
  return http.get<ThreadDetail>(`/api/v1/llm/threads/${id}`, { token })
}

export function deleteThread(token: string, id: string) {
  return http.delete(`/api/v1/llm/threads/${id}`, { token })
}

export interface LangsmithInfo {
  enabled: boolean
  ui_url: string
  project?: string
}

export function getLangsmithInfo(token: string) {
  return http.get<LangsmithInfo>('/api/v1/llm/langsmith/info', { token })
}

export async function* chatStream(token: string, data: ChatRequest): AsyncGenerator<StreamChunk> {
  const baseURL = resolveBaseURL()
  const fetchURL = baseURL.endsWith('/') ? `${baseURL}api/v1/llm/chat/stream` : `${baseURL}/api/v1/llm/chat/stream`
  const response = await fetch(fetchURL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'Accept': 'text/plain'
    },
    body: JSON.stringify(data),
    cache: 'no-store'
  })
  if (!response.ok) {
     const text = await response.text();
     throw new Error(text || response.statusText);
  }
  if (!response.body) throw new Error('ReadableStream not supported')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const chunk = JSON.parse(line) as StreamChunk
          yield chunk
        } catch {
          console.warn('Failed to parse stream chunk:', line)
        }
      }
    }
    if (buffer.trim()) {
       try {
          const chunk = JSON.parse(buffer) as StreamChunk
          yield chunk
       } catch {
          console.warn('Failed to parse last stream chunk:', buffer)
       }
    }
  } finally {
    reader.releaseLock()
  }
}
