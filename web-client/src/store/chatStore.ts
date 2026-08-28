/**
 * 聊天状态 — 对应安卓端 ChatViewModel.kt + ChatUiState.kt。
 *
 * 核心链路：onSend → SSE 流式 (connectStream)，token 逐字到达实时显示，
 * done 后用 result 补全商品/决策/证据/轨迹。
 * 另含：问欧米(聚焦分析)、语音(ASR+TTS)、图片上传、历史会话。
 */
import { create } from 'zustand'
import { api } from '@/api/client'
import { connectStream } from '@/api/stream'
import type {
  ConversationItem,
  DecisionResult,
  EvidenceItem,
  Product,
  TraceStepItem,
  MessageStatus,
  RecommendResponse,
  RetrievalPlan,
  Comparison,
  FocusAnalysis,
  ShopCard,
  ClarificationOption,
  ChatAction,
} from '@/api/types'
import { getEffectiveUserId } from './authStore'
import { shortId } from '@/lib/utils'
import { resolveImageUrl } from '@/config'

export type MascotPhase = 'idle' | 'searching' | 'analyzing' | 'talking'

export type Role = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: Role
  text: string
  products: Product[]
  decisionResults: DecisionResult[]
  evidenceList: EvidenceItem[]
  traceSteps: TraceStepItem[]
  retrievalPlan?: RetrievalPlan | null
  sufficiencyReport?: Record<string, unknown> | null
  constraints?: Record<string, unknown> | null
  harnessReport?: Record<string, unknown> | null
  focusAnalysis?: FocusAnalysis | null
  comparison?: Comparison | null
  shopCard?: ShopCard | null
  clarificationOptions?: ClarificationOption[] | null
  actions?: ChatAction[] | null
  status?: MessageStatus
  imageUrl?: string | null
  isVoice?: boolean
  productResolution?: Record<string, unknown> | null
  visualResult?: Record<string, unknown> | null
}

interface ChatState {
  sessionId: string
  conversationId: string
  messages: ChatMessage[]
  streamingText: string
  isStreaming: boolean
  phase: MascotPhase
  loadingMessage: string
  /** Event-v1 payloads received before final result; shown instead of waiting. */
  streamingPreview: Partial<RecommendResponse> | null
  error: string | null
  deepThink: boolean // 深度思考：OmniAgent ReAct Loop（LLM 自主调工具，更慢但更彻底）

  // 输入区图片
  pendingImageFile: File | null
  pendingImagePreview: string | null

  // 语音
  isRecording: boolean
  recordingSeconds: number
  voicePlaying: boolean

  // 历史
  conversations: ConversationItem[]
  isLoadingHistory: boolean

  // 内部
  _abort: (() => void) | null
  _requestId: number

  send: (query: string) => Promise<void>
  askAgent: (productId: string, title: string, compare?: boolean) => Promise<void>
  stop: () => void
  setDeepThink: (v: boolean) => void
  setPendingImage: (file: File | null) => void
  clearError: () => void
  newConversation: () => void
  // 聊天列表滚动位置（会话级内存态）：从详情页返回时恢复停留位置而非强制滚底
  chatScrollTop: number | null
  setChatScrollTop: (v: number | null) => void

  loadConversations: () => Promise<void>
  loadConversation: (conversationId: string) => Promise<void>
  deleteConversation: (conversationId: string) => Promise<void>

  transcribe: (blob: Blob, filename: string) => Promise<string | null>
  playTTS: (text: string) => Promise<void>
  setRecording: (v: boolean, seconds?: number) => void
}

function newMsg(role: Role, text = '', extra: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: shortId() + shortId(),
    role,
    text,
    products: [],
    decisionResults: [],
    evidenceList: [],
    traceSteps: [],
    status: 'complete',
    ...extra,
  }
}

/** 从 SSE result JSON 提取组装 assistant 消息字段。 */
function assistantFromResult(
  text: string,
  r: RecommendResponse | null,
  hasUploadedImage = false,
): Partial<ChatMessage> {
  return {
    text,
    products: r?.products ?? [],
    decisionResults: r?.decision_results ?? [],
    evidenceList: r?.evidence_list ?? [],
    traceSteps: r?.trace_steps ?? [],
    retrievalPlan: (r?.retrieval_plan as RetrievalPlan | null | undefined) ?? null,
    sufficiencyReport: r?.sufficiency_report ?? null,
    constraints: r?.constraints ?? null,
    harnessReport: r?.harness_report ?? null,
    focusAnalysis: r?.focus_analysis ?? null,
    comparison: r?.comparison ?? null,
    shopCard: r?.shop_card ?? null,
    clarificationOptions: (r?.clarification_options as ClarificationOption[] | null | undefined) ?? null,
    actions: (r?.actions as ChatAction[] | null | undefined) ?? null,
    productResolution: (r?.product_resolution as Record<string, unknown> | null | undefined) ?? null,
    // A visual recognition badge belongs only to the assistant reply that
    // follows an actual user upload.  This client-side guard also protects old
    // cached/backend responses that accidentally contain a stale visual field.
    visualResult: hasUploadedImage ? (r?.visual_result ?? null) : null,
    status: 'complete',
  }
}

let audioEl: HTMLAudioElement | null = null
let audioUrl: string | null = null

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: shortId(),
  conversationId: '',
  messages: [],
  streamingText: '',
  isStreaming: false,
  phase: 'idle',
  loadingMessage: '',
  streamingPreview: null,
  error: null,
  deepThink: false,
  pendingImageFile: null,
  pendingImagePreview: null,
  isRecording: false,
  recordingSeconds: 0,
  voicePlaying: false,
  conversations: [],
  isLoadingHistory: false,
  _abort: null,
  _requestId: 0,

  setDeepThink: (v) => set({ deepThink: v }),
  clearError: () => set({ error: null }),
  chatScrollTop: null,
  setChatScrollTop: (v) => set({ chatScrollTop: v }),

  setPendingImage: (file) => {
    const prev = get().pendingImagePreview
    if (prev) URL.revokeObjectURL(prev)
    set({
      pendingImageFile: file,
      pendingImagePreview: file ? URL.createObjectURL(file) : null,
    })
  },

  newConversation: () => {
    get()._abort?.()
    const state = get()
    if (state.pendingImagePreview) URL.revokeObjectURL(state.pendingImagePreview)
    state.messages.forEach((message) => {
      if (message.imageUrl?.startsWith('blob:')) URL.revokeObjectURL(message.imageUrl)
    })
    if (audioEl) audioEl.pause()
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    audioEl = null
    audioUrl = null
    set({
      sessionId: shortId(),
      conversationId: '',
      messages: [],
      streamingText: '',
      isStreaming: false,
      phase: 'idle',
      error: null,
      chatScrollTop: null,
      pendingImageFile: null,
      pendingImagePreview: null,
      _abort: null,
      _requestId: state._requestId + 1,
      voicePlaying: false,
    })
  },

  stop: () => {
    const state = get()
    state._abort?.()
    const stoppedMessage = state.streamingText
      ? newMsg('assistant', state.streamingText, { status: 'stopped' })
      : null
    set({
      isStreaming: false,
      streamingText: '',
      phase: 'idle',
      _abort: null,
      _requestId: state._requestId + 1,
      messages: stoppedMessage ? [...state.messages, stoppedMessage] : state.messages,
    })
  },

  send: async (query) => {
    const q = query.trim()
    const imageFile = get().pendingImageFile
    if (!q && !imageFile) return

    const finalQuery = q || '请帮我分析这张图片里的商品'
    get()._abort?.()
    const requestId = get()._requestId + 1

    // 先上传图片（如有）
    let imageUrl: string | null = null
    const localPreview = get().pendingImagePreview
    if (imageFile) {
      try {
        const up = await api.uploadImage(imageFile)
        imageUrl = up.image_url
      } catch {
        set({ error: '图片上传失败，请重试' })
        return
      }
    }

    const userMsg = newMsg('user', finalQuery, { imageUrl: localPreview })
    set((s) => ({
      messages: [...s.messages, userMsg],
      isStreaming: true,
      streamingText: '',
      error: null,
      loadingMessage: '欧米正在帮你找商品…',
      streamingPreview: null,
      phase: 'searching',
      pendingImageFile: null,
      pendingImagePreview: null,
      _requestId: requestId,
    }))

    let fullText = ''
    let resultData: RecommendResponse | null = null

    const { abort, done } = connectStream(
      {
        session_id: get().sessionId,
        user_id: getEffectiveUserId(),
        conversation_id: get().conversationId,
        message: finalQuery,
        image_url: imageUrl,
        deep_think: get().deepThink,
      },
      {
        onToken: (t) => {
          if (get()._requestId !== requestId) return
          fullText += t
          set({ streamingText: fullText, phase: 'talking' })
        },
        // 后端 status 中间态（如“欧米正在挑选好物…”）刷新加载文案
        onStatus: (text) => {
          if (get()._requestId === requestId) set({ loadingMessage: text })
        },
        onEvent: (type, payload) => {
          if (get()._requestId !== requestId || !payload || typeof payload !== 'object') return
          const data = payload as Record<string, unknown>
          if (type === 'recommendations') {
            set({ streamingPreview: data as Partial<RecommendResponse> })
          } else if (type === 'visual_result' || type === 'focus_analysis' || type === 'comparison') {
            set((state) => ({
              streamingPreview: {
                ...(state.streamingPreview ?? {}),
                ...(type === 'visual_result'
                  ? {
                      visual_result: data.visual_result as Record<string, unknown> | null | undefined,
                      product_resolution: data.product_resolution as Record<string, unknown> | null | undefined,
                    }
                  : { [type]: data }),
              },
            }))
          }
        },
        onResult: (r) => {
          resultData = r
        },
        onError: (m) => {
          if (get()._requestId === requestId) set({ error: m })
        },
      },
    )
    set({ _abort: abort })

    await done

    if (get()._requestId !== requestId) return

    const rd = resultData as RecommendResponse | null
    const answer = fullText || rd?.answer || ''
    const convId = rd?.conversation_id || ''
    if (!answer) {
      set({ isStreaming: false, streamingText: '', phase: 'idle', _abort: null })
      return
    }
    const assistantMsg = newMsg('assistant', answer, assistantFromResult(answer, rd, Boolean(imageUrl)))

    set((s) => ({
      isStreaming: false,
      streamingText: '',
      streamingPreview: null,
      phase: 'idle',
      _abort: null,
      messages: [...s.messages, assistantMsg],
      conversationId: convId || s.conversationId,
    }))
  },

  askAgent: async (productId, title, compare = false) => {
    get()._abort?.()
    const requestId = get()._requestId + 1
    const query = compare
      ? `请把「${title}」与同类商品横向对比，说明主要差异、分别适合谁，以及我该怎么选。`
      : `帮我分析一下「${title}」`
    const userMsg = newMsg('user', query)
    set((s) => ({
      messages: [...s.messages, userMsg],
      isStreaming: true,
      streamingText: '',
      error: null,
      loadingMessage: compare
        ? `欧米正在为你横向比较「${title.slice(0, 15)}」…`
        : `欧米正在分析「${title.slice(0, 15)}」…`,
      streamingPreview: null,
      phase: 'analyzing',
      _requestId: requestId,
    }))

    let fullText = ''
    let resultData: RecommendResponse | null = null

    const { abort, done } = connectStream(
      {
        session_id: get().sessionId,
        user_id: getEffectiveUserId(),
        conversation_id: get().conversationId,
        message: query,
        mode: compare ? 'same_category_comparison' : 'product_focused_analysis',
        target_product_id: productId,
        // “问欧米”同样应尊重用户已开启的深度思考开关。此前这个入口漏传，
        // 即使界面显示已开启也永远走普通单品路径。
        deep_think: get().deepThink,
        // 单品分析默认不混入同类；用户点选“横向对比”时才明确授权扩展范围。
        allow_same_category_comparison: compare,
      },
      {
        onToken: (t) => {
          if (get()._requestId !== requestId) return
          fullText += t
          set({ streamingText: fullText, phase: 'talking' })
        },
        onStatus: (text) => {
          if (get()._requestId === requestId) set({ loadingMessage: text })
        },
        onEvent: (type, payload) => {
          if (get()._requestId !== requestId || !payload || typeof payload !== 'object') return
          const data = payload as Record<string, unknown>
          if (type === 'recommendations') set({ streamingPreview: data as Partial<RecommendResponse> })
          else if (type === 'visual_result' || type === 'focus_analysis' || type === 'comparison') {
            set((state) => ({ streamingPreview: {
              ...(state.streamingPreview ?? {}),
              ...(type === 'visual_result'
                ? {
                    visual_result: data.visual_result as Record<string, unknown> | null | undefined,
                    product_resolution: data.product_resolution as Record<string, unknown> | null | undefined,
                  }
                : { [type]: data }),
            } }))
          }
        },
        onResult: (r) => {
          resultData = r
        },
        onError: (m) => {
          if (get()._requestId === requestId) set({ error: m })
        },
      },
    )
    set({ _abort: abort })
    await done

    if (get()._requestId !== requestId) return

    const rd = resultData as RecommendResponse | null
    const answer = fullText || rd?.answer || ''
    const convId = rd?.conversation_id || ''
    if (!answer) {
      set({ isStreaming: false, streamingText: '', phase: 'idle', _abort: null })
      return
    }
    const assistantMsg = newMsg('assistant', answer, assistantFromResult(answer, rd, false))
    set((s) => ({
      isStreaming: false,
      streamingText: '',
      streamingPreview: null,
      phase: 'idle',
      _abort: null,
      messages: [...s.messages, assistantMsg],
      conversationId: convId || s.conversationId,
    }))
  },

  loadConversations: async () => {
    const uid = getEffectiveUserId()
    if (!uid) return
    set({ isLoadingHistory: true })
    try {
      const res = await api.getConversations(uid)
      set({ conversations: res.conversations, isLoadingHistory: false })
    } catch {
      set({ isLoadingHistory: false })
    }
  },

  loadConversation: async (conversationId) => {
    get()._abort?.()
    const requestId = get()._requestId + 1
    set({ _requestId: requestId, isStreaming: false, streamingText: '', _abort: null })
    try {
      const res = await api.getConversationMessages(conversationId)
      const productsMap = res.products ?? {}
      const msgs: ChatMessage[] = res.messages.map((m) => {
        const prods: Product[] = (m.product_refs || [])
          .map((pid) => productsMap[pid])
          .filter(Boolean)
          .map((p) => ({
            product_id: String((p as Record<string, unknown>).product_id ?? ''),
            title: String((p as Record<string, unknown>).title ?? ''),
            brand: String((p as Record<string, unknown>).brand ?? ''),
            category: String((p as Record<string, unknown>).category ?? ''),
            sub_category: '',
            price: Number((p as Record<string, unknown>).price ?? 0),
            image_urls: ((p as Record<string, unknown>).image_urls as string[]) ?? [],
          }))
        return newMsg(m.role === 'user' ? 'user' : 'assistant', m.content, {
          products: prods,
          imageUrl: m.image_url ? resolveImageUrl(m.image_url) : null,
        })
      })
      if (get()._requestId === requestId) set({ conversationId, messages: msgs, error: null })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '加载对话失败' })
    }
  },

  deleteConversation: async (conversationId) => {
    try {
      await api.deleteConversation(conversationId)
      await get().loadConversations()
      if (get().conversationId === conversationId) get().newConversation()
    } catch (e) {
      set({ error: e instanceof Error ? e.message : '删除失败' })
    }
  },

  transcribe: async (blob, filename) => {
    try {
      const res = await api.voiceTranscribe(blob, filename)
      if (res.fallback || !res.text.trim()) return null
      return res.text.trim()
    } catch {
      return null
    }
  },

  playTTS: async (text) => {
    const t = text.slice(0, 300).trim()
    if (!t) return
    try {
      set({ voicePlaying: true })
      const resp = await api.voiceTTS(t)
      if (!resp.ok) {
        set({ voicePlaying: false })
        return
      }
      const buf = await resp.arrayBuffer()
      if (buf.byteLength < 100) {
        set({ voicePlaying: false })
        return
      }
      const url = URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }))
      if (audioEl) {
        audioEl.pause()
      }
      if (audioUrl) URL.revokeObjectURL(audioUrl)
      audioUrl = url
      audioEl = new Audio(url)
      audioEl.onended = () => {
        set({ voicePlaying: false })
        URL.revokeObjectURL(url)
        if (audioUrl === url) audioUrl = null
      }
      audioEl.onerror = () => {
        set({ voicePlaying: false })
        URL.revokeObjectURL(url)
        if (audioUrl === url) audioUrl = null
      }
      await audioEl.play()
    } catch {
      set({ voicePlaying: false })
    }
  },

  setRecording: (v, seconds = 0) => set({ isRecording: v, recordingSeconds: seconds }),
}))
