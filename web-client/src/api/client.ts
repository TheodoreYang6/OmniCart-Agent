/**
 * OmniCart HTTP 客户端。
 *
 * 对齐安卓端 OmniCartApi.kt 的接口定义与 ApiClient.kt 的鉴权拦截器
 * （自动注入 Authorization: Bearer <token>）。
 */
import { apiUrl, REQUEST_TIMEOUT_MS } from '@/config'
import { getToken } from '@/store/authStore'
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
  ConversationListResponse,
  ConversationMessagesResponse,
  GuideRequest,
  GuideResponse,
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

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

interface RequestOptions {
  method?: string
  query?: Record<string, string | number | boolean | undefined | null>
  body?: unknown
  isForm?: boolean
  timeoutMs?: number
  raw?: boolean // 返回原始 Response（用于二进制 / TTS）
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

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, isForm, timeoutMs = REQUEST_TIMEOUT_MS, raw } = opts
  const url = apiUrl(path) + buildQuery(query)

  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

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
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const resp = await fetch(url, { method, headers, body: payload, signal: controller.signal })
    if (raw) return resp as unknown as T

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
      const detail =
        (data && typeof data === 'object' && 'detail' in data
          ? String((data as Record<string, unknown>).detail)
          : '') || `请求失败 (${resp.status})`
      throw new ApiError(resp.status, detail)
    }
    return data as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(0, '请求超时，请检查网络或后端服务')
    }
    throw new ApiError(0, err instanceof Error ? err.message : '网络请求失败')
  } finally {
    clearTimeout(timer)
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
  } = {}) => request<ProductListResponse>('/api/products', { query: params }),

  getProduct: (productId: string) =>
    request<ProductDetail>(`/api/products/${encodeURIComponent(productId)}`),

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

  getOrders: (userId: string) =>
    request<OrderListResponse>('/api/orders', { query: { user_id: userId } }),

  // ---- 认证 ----
  register: (body: { username: string; password: string; email?: string; phone?: string }) =>
    request<AuthResponse>('/api/auth/register', { method: 'POST', body }),

  login: (body: { username: string; password: string }) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body }),

  profile: () => request<AuthResponse>('/api/auth/profile'),

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
    const resp = await fetch(
      apiUrl(`/api/products/${encodeURIComponent(productId)}/ai-summary`),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query ?? '' }),
        signal,
      },
    )
    if (!resp.ok || !resp.body) {
      throw new ApiError(resp.status, '总结生成失败')
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const blocks = buf.split('\n\n')
      buf = blocks.pop() ?? ''
      for (const b of blocks) {
        const line = b.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        try {
          const payload = JSON.parse(line.slice(6)) as { text?: string }
          if (payload.text) onChunk(payload.text)
        } catch {
          /* 忽略非 JSON 心跳/done 事件 */
        }
      }
    }
  },
}

export type Api = typeof api
