import { apiUrl } from '@/config'
import { buildAuthHeaders } from '@/api/client'
import { parseSseFrames, type ParsedSseEvent } from './sse'
import type { RecommendResponse } from '@/api/types'

export { parseSseFrames } from './sse'

export interface StreamRequest {
  session_id?: string
  user_id?: string
  conversation_id?: string
  message: string
  image_url?: string | null
  mode?: string
  target_product_id?: string | null
  allow_same_category_comparison?: boolean
  exec_mode?: string
  deep_think?: boolean
}

export type StreamFinishReason = 'complete' | 'aborted' | 'error'

export interface StreamHandlers {
  onToken?: (text: string) => void
  onStatus?: (text: string) => void
  onResult?: (result: RecommendResponse) => void
  onError?: (message: string) => void
  onDone?: (reason: StreamFinishReason) => void
  /** All protocol v1 events, including early cards/visual/comparison payloads. */
  onEvent?: (type: string, payload: unknown) => void
}

function messageFromData(data: string, fallback: string): string {
  try {
    const parsed = JSON.parse(data) as { text?: string; message?: string }
    return parsed.text ?? parsed.message ?? fallback
  } catch {
    return fallback
  }
}

export function connectStream(
  req: StreamRequest,
  handlers: StreamHandlers,
): { abort: () => void; done: Promise<StreamFinishReason> } {
  const controller = new AbortController()
  let finishReason: StreamFinishReason = 'complete'
  let notified = false

  const notifyDone = (reason: StreamFinishReason) => {
    if (notified) return
    notified = true
    handlers.onDone?.(reason)
  }

  const done = (async (): Promise<StreamFinishReason> => {
    try {
      const resp = await fetch(apiUrl('/api/recommend/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...buildAuthHeaders(),
        },
        body: JSON.stringify(req),
        signal: controller.signal,
        credentials: 'include',
      })
      if (!resp.ok || !resp.body) {
        let message = `服务异常 (${resp.status})`
        try {
          const payload = await resp.json() as { detail?: string }
          message = payload.detail || message
        } catch { /* response may not be JSON */ }
        handlers.onError?.(message)
        if (resp.status === 401 && typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('omnicart:unauthorized', { detail: { path: '/api/recommend/stream' } }))
        }
        finishReason = 'error'
        return finishReason
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''

      const dispatch = (event: ParsedSseEvent) => {
        let payload: unknown = event.data
        try { payload = JSON.parse(event.data) } catch { /* plain heartbeat/text */ }
        handlers.onEvent?.(event.type, payload)
        if (event.type === 'token') handlers.onToken?.(messageFromData(event.data, ''))
        else if (event.type === 'status' || event.type === 'stage') handlers.onStatus?.(messageFromData(event.data, ''))
        else if (event.type === 'result') {
          try { handlers.onResult?.(JSON.parse(event.data) as RecommendResponse) }
          catch { handlers.onError?.('服务返回了无效的结果数据') }
        } else if (event.type === 'error') {
          handlers.onError?.(messageFromData(event.data, '服务异常'))
          finishReason = 'error'
        }
      }

      for (;;) {
        const chunk = await reader.read()
        if (chunk.done) break
        buffer += decoder.decode(chunk.value, { stream: true })
        const parsed = parseSseFrames(buffer)
        buffer = parsed.rest
        parsed.events.forEach(dispatch)
      }
      buffer += decoder.decode()
      parseSseFrames(buffer, true).events.forEach(dispatch)
    } catch (error) {
      if (controller.signal.aborted) finishReason = 'aborted'
      else {
        finishReason = 'error'
        handlers.onError?.(error instanceof Error ? error.message : '流读取失败')
      }
    } finally {
      notifyDone(finishReason)
    }
    return finishReason
  })()

  return { abort: () => controller.abort('user'), done }
}
