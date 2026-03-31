import { http, resolveBaseURL } from '@/api/http'

export interface ToolCall {
  id: string
  name: string
  args?: Record<string, unknown>
  result?: unknown
  status: 'running' | 'done' | 'error'
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  created_at?: string
  toolCalls?: ToolCall[]
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
}

export interface ChatResponse {
  final_response: string
  thread_id: string
}

export interface StreamChunk {
  type: 'id' | 'text_delta' | 'tool_start' | 'tool_end' | 'done' | 'error'
  content?: unknown
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

export async function* chatStream(token: string, data: ChatRequest): AsyncGenerator<StreamChunk> {
  const baseURL = resolveBaseURL()
  const fetchURL = baseURL.endsWith('/') ? `${baseURL}api/v1/llm/chat/stream` : `${baseURL}/api/v1/llm/chat/stream`
  const response = await fetch(fetchURL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'Accept': 'text/event-stream'
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
      
      let eventEndIndex = buffer.indexOf('\n\n')
      while (eventEndIndex !== -1) {
        const eventText = buffer.slice(0, eventEndIndex)
        buffer = buffer.slice(eventEndIndex + 2)
        
        let eventType = 'message'
        let eventData = ''
        
        for (const line of eventText.split('\n')) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            eventData = line.slice(5).trim()
          }
        }
        
        if (eventData) {
          try {
            // data should be JSON according to spec
            const parsedData = JSON.parse(eventData)
            yield {
              type: eventType as StreamChunk['type'],
              content: parsedData
            }
          } catch {
            // Some events like 'done' might not be JSON, fallback to raw string
            yield {
              type: eventType as StreamChunk['type'],
              content: eventData
            }
          }
        } else if (eventType === 'done') {
           yield { type: 'done' }
        }
        
        eventEndIndex = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}
