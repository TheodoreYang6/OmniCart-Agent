/**
 * OmniCart HTTP 客户端。
 *
 * 对齐安卓端 OmniCartApi.kt 的接口定义与 ApiClient.kt 的鉴权拦截器
 * （自动注入 Authorization: Bearer <token>）。
 */
import { apiUrl, REQUEST_TIMEOUT_MS } from '@/config'
import { getToken } from '@/store/authStore'
import { parseSseFrames } from './sse'
import type {
  AddToCartRequest,
  Address,
  AddressCreateRequest,
  AddressListResponse,
  AddressUpdateRequest,
  AuthResponse,
  CartResponse,
  CheckoutRequest,
  CheckoutResponse,
  CheckoutPreviewResponse,
  CheckoutSubmitResponse,
  ConversationListResponse,
  ConversationMessagesResponse,
  GuideRequest,
  GuideResponse,
  GuestResponse,
  HealthResponse,
  OkResponse,
  OrderListResponse,
  ParseResultResponse,
  PreferenceEntriesResponse,
  PreferenceSaveResultResponse,
  ProductDetail,
  ProductListResponse,
  RecommendRequest,
  RecommendResponse,
  TranscribeResponse,
  UploadResponse,
} from './types'

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'aborted'

export class ApiError extends Error {
  status: number
  code?: string
  kind: ApiErrorKind
  constructor(status: number, message: string, code?: string, kind: ApiErrorKind = status > 0 ? 'http' : 'network') {
    super(message)
    this.status = status
    this.name = 'ApiError'
    this.code = code
    this.kind = kind
  }
}

interface RequestOptions {
  method?: string
  query?: Record<string, string | number | boolean | undefined | null>
  body?: unknown
  isForm?: boolean
  timeoutMs?: number
  raw?: boolean // 返回原始 Response（用于二进制 / TTS）
  signal?: AbortSignal
  skipUnauthorizedEvent?: boolean
}

function buildQuery(query?: RequestOptions['query']): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.append(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

export function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, isForm, timeoutMs = REQUEST_TIMEOUT_MS, raw, signal, skipUnauthorizedEvent } = opts
  const url = apiUrl(path) + buildQuery(query)

  const headers = buildAuthHeaders()

  let payload: BodyInit | undefined
  if (body !== undefined && body !== null) {
    if (isForm) {
      payload = body as FormData
    } else {
      headers['Content-Type'] = 'application/json'
      payload = JSON.stringify(body)
    }
  }

  const controller = new AbortController()
  let didTimeout = false
  const timer = setTimeout(() => {
    didTimeout = true
    controller.abort('timeout')
  }, timeoutMs)
  const onAbort = () => controller.abort(signal?.reason)
  signal?.addEventListener('abort', onAbort, { once: true })

  try {
    const resp = await fetch(url, {
      method,
      headers,
      body: payload,
      signal: controller.signal,
      credentials: 'include',
    })

    if (raw && resp.ok) return resp as unknown as T

    const text = await resp.text()
    let data: unknown = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        data = text
      }
    }

    if (!resp.ok) {
      const payloadData = data && typeof data === 'object' ? data as Record<string, unknown> : {}
      const detailValue = payloadData.detail ?? payloadData.message
      const detail = Array.isArray(detailValue)
        ? detailValue.map((item) => typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)).join('；')
        : String(detailValue ?? '') || `请求失败 (${resp.status})`
      if (resp.status === 401 && !skipUnauthorizedEvent && typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('omnicart:unauthorized', { detail: { path } }))
      }
      throw new ApiError(resp.status, detail, typeof payloadData.code === 'string' ? payloadData.code : undefined)
    }
    return data as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (signal?.aborted) {
      throw new ApiError(0, '请求已取消', undefined, 'aborted')
    }
    if (didTimeout) {
      throw new ApiError(0, '请求超时，请检查网络或后端服务', undefined, 'timeout')
    }
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(0, '请求已取消', undefined, 'aborted')
    }
    throw new ApiError(0, err instanceof Error ? err.message : '网络请求失败', undefined, 'network')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }
}

export const api = {
  // ---- 健康 ----
  health: () => request<HealthResponse>('/api/health'),

  // ---- 商品 ----
  getProducts: (params: {
    category?: string
    sub_category?: string
    keyword?: string
    price_min?: number
    price_max?: number
    page?: number
    page_size?: number
  } = {}, signal?: AbortSignal) => request<ProductListResponse>('/api/products', { query: params, signal }),

  getProduct: (productId: string, signal?: AbortSignal) =>
    request<ProductDetail>(`/api/products/${encodeURIComponent(productId)}`, { signal }),

  // ---- 推荐 ----
  recommend: (req: RecommendRequest) =>
    request<RecommendResponse>('/api/recommend/v2', { method: 'POST', body: req }),

  recommendGuide: (req: GuideRequest) =>
    request<GuideResponse>('/api/recommend/guide', { method: 'POST', body: req }),

  // ---- 对话历史 ----
  getConversations: (userId: string) =>
    request<ConversationListResponse>('/api/conversations', { query: { user_id: userId } }),

  getConversationMessages: (conversationId: string) =>
    request<ConversationMessagesResponse>(
      `/api/conversations/${encodeURIComponent(conversationId)}/messages`,
    ),

  deleteConversation: (conversationId: string) =>
    request<OkResponse>(`/api/conversations/${encodeURIComponent(conversationId)}`, {
      method: 'DELETE',
    }),

  // ---- 上传 ----
  uploadImage: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<UploadResponse>('/api/upload', { method: 'POST', body: form, isForm: true })
  },

  // ---- 购物车 ----
  getCart: (ctx: { user_id?: string; session_id?: string; conversation_id?: string }) =>
    request<CartResponse>('/api/cart', { query: ctx }),

  addToCart: (
    item: AddToCartRequest,
    ctx: { user_id?: string; session_id?: string; conversation_id?: string } = {},
  ) => request<CartResponse['items'][number]>('/api/cart/items', { method: 'POST', body: item, query: ctx }),

  updateCartItem: (
    cartItemId: string,
    update: { quantity?: number | null; selected?: boolean | null },
    ctx: { user_id?: string; session_id?: string; conversation_id?: string } = {},
  ) =>
    request<CartResponse['items'][number]>(`/api/cart/items/${encodeURIComponent(cartItemId)}`, {
      method: 'PUT',
      body: update,
      query: ctx,
    }),

  removeCartItem: (
    cartItemId: string,
    ctx: { user_id?: string; session_id?: string; conversation_id?: string } = {},
  ) =>
    request<OkResponse>(`/api/cart/items/${encodeURIComponent(cartItemId)}`, {
      method: 'DELETE',
      query: ctx,
    }),

  selectAllCart: (
    selected: boolean,
    ctx: { user_id?: string; session_id?: string; conversation_id?: string } = {},
  ) => request<OkResponse>('/api/cart/select-all', { method: 'POST', query: { selected, ...ctx } }),

  clearCart: (ctx: { user_id?: string; session_id?: string; conversation_id?: string } = {}) =>
    request<OkResponse>('/api/cart/clear', { method: 'DELETE', query: ctx }),

  // ---- 结算 / 订单 ----
  checkout: (req: CheckoutRequest) =>
    request<CheckoutResponse>('/api/checkout', { method: 'POST', body: req }),

  checkoutPreview: (req: CheckoutRequest) =>
    request<CheckoutPreviewResponse>('/api/checkout/preview', { method: 'POST', body: req }),

  checkoutSubmit: (req: CheckoutRequest) =>
    request<CheckoutSubmitResponse>('/api/checkout/submit', { method: 'POST', body: req }),

  getOrders: (userId: string) =>
    request<OrderListResponse>('/api/orders', { query: { user_id: userId } }),

  // ---- 认证 ----
  register: (body: { username: string; password: string; email?: string; phone?: string }) =>
    request<AuthResponse>('/api/auth/register', { method: 'POST', body, skipUnauthorizedEvent: true }),

  login: (body: { username: string; password: string }) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body, skipUnauthorizedEvent: true }),

  profile: () => request<AuthResponse>('/api/auth/profile', { skipUnauthorizedEvent: true }),
  guest: () => request<GuestResponse>('/api/auth/guest', { method: 'POST', skipUnauthorizedEvent: true }),
  logout: () => request<GuestResponse & { ok: boolean }>('/api/auth/logout', { method: 'POST', skipUnauthorizedEvent: true }),

  // ---- 地址 ----
  getAddresses: (userId: string) =>
    request<AddressListResponse>('/api/addresses', { query: { user_id: userId } }),

  createAddress: (req: AddressCreateRequest, userId: string) =>
    request<Address>('/api/addresses', { method: 'POST', body: req, query: { user_id: userId } }),

  updateAddress: (addressId: string, req: AddressUpdateRequest, userId: string) =>
    request<Address>(`/api/addresses/${encodeURIComponent(addressId)}`, {
      method: 'PUT',
      body: req,
      query: { user_id: userId },
    }),

  deleteAddress: (addressId: string, userId: string) =>
    request<OkResponse>(`/api/addresses/${encodeURIComponent(addressId)}`, {
      method: 'DELETE',
      query: { user_id: userId },
    }),

  // ---- 偏好条目 (V3) ----
  getPreferenceEntries: (userId: string) =>
    request<PreferenceEntriesResponse>('/api/preferences/entries', {
      query: { user_id: userId },
    }),

  parsePreference: (userId: string, rawText: string) =>
    request<ParseResultResponse>('/api/preferences/parse', {
      method: 'POST',
      body: { user_id: userId, raw_text: rawText },
    }),

  savePreferenceEntry: (userId: string, rawText: string, entryId = '') =>
    request<PreferenceSaveResultResponse>('/api/preferences/entries', {
      method: 'PUT',
      body: { user_id: userId, raw_text: rawText, entry_id: entryId },
    }),

  deletePreferenceEntry: (entryId: string, userId: string) =>
    request<OkResponse>(`/api/preferences/entries/${encodeURIComponent(entryId)}`, {
      method: 'DELETE',
      query: { user_id: userId },
    }),

  togglePreferenceEntry: (entryId: string, userId: string, enabled: boolean) =>
    request<OkResponse>(`/api/preferences/entries/${encodeURIComponent(entryId)}/toggle`, {
      method: 'PUT',
      query: { user_id: userId, enabled },
    }),

  // ---- 语音 ----
  voiceTranscribe: (audio: Blob, filename = 'voice.webm') => {
    const form = new FormData()
    form.append('audio', audio, filename)
    return request<TranscribeResponse>('/api/voice/transcribe', {
      method: 'POST',
      body: form,
      isForm: true,
    })
  },

  voiceTTS: (text: string, voice = 'Cherry') =>
    request<Response>('/api/voice/tts', {
      method: 'POST',
      body: { text, voice },
      raw: true,
    }),

  // ---- 商品 AI 小总结（SSE 流式，Spotlight 面板异步加载）----
  /**
   * 流式拉取商品小总结，逐块回调文本。
   * @param productId 商品 id
   * @param query 用户当轮需求（使总结贴合上下文）
   * @param onChunk 每收到一段文本回调（增量）
   * @param signal 供组件卸载时中断
   */
  streamProductSummary: async (
    productId: string,
    query: string,
    onChunk: (text: string) => void,
    signal?: AbortSignal,
  ): Promise<void> => {
    try {
      const resp = await fetch(
        apiUrl(`/api/products/${encodeURIComponent(productId)}/ai-summary`),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...buildAuthHeaders() },
          body: JSON.stringify({ query: query ?? '' }),
          signal,
          credentials: 'include',
        },
      )
      if (!resp.ok || !resp.body) {
        throw new ApiError(resp.status, '总结生成失败')
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      const dispatch = (data: string) => {
        try {
          const payload = JSON.parse(data) as { text?: string }
          if (payload.text) onChunk(payload.text)
        } catch {
          // heartbeat/done frames intentionally carry no summary text.
        }
      }
      for (;;) {
        const chunk = await reader.read()
        if (chunk.done) break
        buffer += decoder.decode(chunk.value, { stream: true })
        const parsed = parseSseFrames(buffer)
        buffer = parsed.rest
        parsed.events.forEach((event) => dispatch(event.data))
      }
      buffer += decoder.decode()
      parseSseFrames(buffer, true).events.forEach((event) => dispatch(event.data))
    } catch (error) {
      if (error instanceof ApiError) throw error
      if (signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
        throw new ApiError(0, '请求已取消', undefined, 'aborted')
      }
      throw new ApiError(0, error instanceof Error ? error.message : '总结读取失败', undefined, 'network')
    }
  },
}

export type Api = typeof api
