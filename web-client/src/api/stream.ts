/**
 * SSE 流式客户端 — 对应安卓端 AgentStreamClient.kt。
 *
 * 后端 /api/recommend/stream 使用 POST + text/event-stream。
 * 浏览器原生 EventSource 仅支持 GET，因此改用 fetch + ReadableStream 手动解析
 * `event:` / `data:` 行。
 *
 * 事件类型：token(逐字文本) / status(中间态提示) / result(完整 RecommendResponse) / error / done
 */
import { apiUrl } from '@/config'
import { getToken } from '@/store/authStore'

export interface StreamRequest {
  session_id?: string
  user_id?: string
  conversation_id?: string
  message: string
  image_url?: string | null
  mode?: string // normal_recommend | product_focused_analysis
  target_product_id?: string | null
  allow_same_category_comparison?: boolean
  fast_mode?: boolean
  exec_mode?: string // 执行档位 lite/standard/max（max=动态编排按请求灰度），与业务场景 mode 无关
  deep_think?: boolean // 深度思考：OmniAgent Loop 预算 3→8 轮（Phase 7）
}

export type SseEventType = 'token' | 'status' | 'result' | 'error' | 'done' | string

export interface SseEvent {
  type: SseEventType
  data: string
}

export interface StreamHandlers {
  onToken?: (text: string) => void
  onStatus?: (text: string) => void // 中间态提示（如“欧米正在挑选好物…”），未订阅则忽略
  onResult?: (result: Record<string, unknown>) => void
  onError?: (message: string) => void
  onDone?: () => void
}

/**
 * 建立 SSE 连接并逐事件回调。返回一个 abort 函数用于中断。
 */
export function connectStream(
  req: StreamRequest,
  handlers: StreamHandlers,
): { abort: () => void; done: Promise<void> } {
  const controller = new AbortController()

  const done = (async () => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    }
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`

    let resp: Response
    try {
      resp = await fetch(apiUrl('/api/recommend/stream'), {
        method: 'POST',
        headers,
        body: JSON.stringify(req),
        signal: controller.signal,
      })
    } catch (e) {
      if ((e as DOMException)?.name === 'AbortError') return
      handlers.onError?.(e instanceof Error ? e.message : '连接失败')
      handlers.onDone?.()
      return
    }

    if (!resp.ok || !resp.body) {
      handlers.onError?.(`服务异常 (${resp.status})`)
      handlers.onDone?.()
      return
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let eventType = ''

    const dispatch = (type: string, data: string) => {
      switch (type) {
        case 'token': {
          let text = ''
          try {
            text = (JSON.parse(data) as { text?: string }).text ?? ''
          } catch {
            /* ignore */
          }
          if (text) handlers.onToken?.(text)
          break
        }
        case 'status': {
          let text = ''
          try {
            text = (JSON.parse(data) as { text?: string }).text ?? ''
          } catch {
            /* ignore */
          }
          if (text) handlers.onStatus?.(text)
          break
        }
        case 'result': {
          try {
            handlers.onResult?.(JSON.parse(data) as Record<string, unknown>)
          } catch {
            /* ignore malformed */
          }
          break
        }
        case 'error': {
          let msg = '服务异常'
          try {
            msg = (JSON.parse(data) as { message?: string }).message ?? msg
          } catch {
            /* ignore */
          }
          handlers.onError?.(msg)
          break
        }
        case 'done': {
          handlers.onDone?.()
          break
        }
      }
    }

    try {
      // 逐行解析 SSE：event: <type> / data: <payload>，空行作为事件分隔。
      // 后端每个事件形如 "event: token\ndata: {...}\n\n"。
      for (;;) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break
        buffer += decoder.decode(value, { stream: true })

        let idx: number
        while ((idx = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, idx).replace(/\r$/, '')
          buffer = buffer.slice(idx + 1)

          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const data = line.slice(5).trim()
            if (eventType) dispatch(eventType, data)
          }
          // 空行 = 事件结束，无需特殊处理（type 会在下个 event: 覆盖）
        }
      }
    } catch (e) {
      if ((e as DOMException)?.name !== 'AbortError') {
        handlers.onError?.(e instanceof Error ? e.message : '流读取失败')
      }
    } finally {
      handlers.onDone?.()
    }
  })()

  return { abort: () => controller.abort(), done }
}
