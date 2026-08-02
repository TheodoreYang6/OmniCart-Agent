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
  retrievalPlan?: Record<string, unknown> | null
  sufficiencyReport?: Record<string, unknown> | null
  constraints?: Record<string, unknown> | null
  harnessReport?: Record<string, unknown> | null
  targetProductAnalysis?: Record<string, unknown> | null
  comparisonTable?: Record<string, unknown> | null
  alternativeProducts?: Array<Record<string, unknown>> | null
  clarificationOptions?: Array<Record<string, unknown>> | null
  actions?: Array<Record<string, unknown>> | null
  imageUrl?: string | null
  isVoice?: boolean
}

interface ChatState {
  sessionId: string
  conversationId: string
  messages: ChatMessage[]
  streamingText: string
  isStreaming: boolean
  phase: MascotPhase
  loadingMessage: string
  error: string | null
  fastMode: boolean
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

  send: (query: string) => Promise<void>
  askAgent: (productId: string, title: string) => Promise<void>
  stop: () => void
  setFastMode: (v: boolean) => void
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
    ...extra,
  }
}

/** 从 SSE result JSON 提取组装 assistant 消息字段。 */
function assistantFromResult(
  text: string,
  r: Record<string, unknown> | null,
): Partial<ChatMessage> {
  const g = <T,>(k: string, dflt: T): T => (r && r[k] !== undefined ? (r[k] as T) : dflt)
  return {
    text,
    products: g<Product[]>('products', []),
    decisionResults: g<DecisionResult[]>('decision_results', []),
    evidenceList: g<EvidenceItem[]>('evidence_list', []),
    traceSteps: g<TraceStepItem[]>('trace_steps', []),
    retrievalPlan: g('retrieval_plan', null) as Record<string, unknown> | null,
    sufficiencyReport: g('sufficiency_report', null) as Record<string, unknown> | null,
    constraints: g('constraints', null) as Record<string, unknown> | null,
    harnessReport: g('harness_report', null) as Record<string, unknown> | null,
    targetProductAnalysis: g('target_product_analysis', null) as Record<string, unknown> | null,
    comparisonTable: g('comparison_table', null) as Record<string, unknown> | null,
    alternativeProducts: g('alternative_products', null) as Array<Record<string, unknown>> | null,
    clarificationOptions: g('clarification_options', null) as Array<Record<string, unknown>> | null,
    actions: g('actions', null) as Array<Record<string, unknown>> | null,
  }
}

let audioEl: HTMLAudioElement | null = null

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: shortId(),
  conversationId: '',
  messages: [],
  streamingText: '',
  isStreaming: false,
  phase: 'idle',
  loadingMessage: '',
  error: null,
  fastMode: false,
  deepThink: false,
  pendingImageFile: null,
  pendingImagePreview: null,
  isRecording: false,
  recordingSeconds: 0,
  voicePlaying: false,
  conversations: [],
  isLoadingHistory: false,
  _abort: null,

  setFastMode: (v) => set({ fastMode: v, ...(v ? { deepThink: false } : {}) }),
  setDeepThink: (v) => set({ deepThink: v, ...(v ? { fastMode: false } : {}) }), // 与极速互斥
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
    })
  },

  stop: () => {
    get()._abort?.()
    set({ isStreaming: false, phase: 'idle', _abort: null })
  },

  send: async (query) => {
    const q = query.trim()
    const imageFile = get().pendingImageFile
    if (!q && !imageFile) return

    const finalQuery = q || '请帮我分析这张图片里的商品'

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
      phase: 'searching',
      pendingImageFile: null,
      pendingImagePreview: null,
    }))

    let fullText = ''
    let resultData: Record<string, unknown> | null = null

    const { abort, done } = connectStream(
      {
        session_id: get().sessionId,
        user_id: getEffectiveUserId(),
        conversation_id: get().conversationId,
        message: finalQuery,
        image_url: imageUrl,
        fast_mode: get().fastMode,
        deep_think: get().deepThink,
      },
      {
        onToken: (t) => {
          fullText += t
          set({ streamingText: fullText, phase: 'talking' })
        },
        // 后端 status 中间态（如“欧米正在挑选好物…”）刷新加载文案
        onStatus: (text) => set({ loadingMessage: text }),
        onResult: (r) => {
          resultData = r
        },
        onError: (m) => set({ error: m }),
      },
    )
    set({ _abort: abort })

    await done

    const rd = resultData as Record<string, unknown> | null
    const answer = fullText || (rd?.answer as string) || '抱歉，暂时无法回答您的问题。'
    const convId = (rd?.conversation_id as string) || ''
    const assistantMsg = newMsg('assistant', answer, assistantFromResult(answer, rd))

    set((s) => ({
      isStreaming: false,
      streamingText: '',
      phase: 'idle',
      _abort: null,
      messages: [...s.messages, assistantMsg],
      conversationId: convId || s.conversationId,
    }))
  },

  askAgent: async (productId, title) => {
    const query = `帮我分析一下「${title}」`
    const userMsg = newMsg('user', query)
    set((s) => ({
      messages: [...s.messages, userMsg],
      isStreaming: true,
      streamingText: '',
      error: null,
      loadingMessage: `欧米正在分析「${title.slice(0, 15)}」…`,
      phase: 'analyzing',
    }))

    let fullText = ''
    let resultData: Record<string, unknown> | null = null

    const { abort, done } = connectStream(
      {
        session_id: get().sessionId,
        user_id: getEffectiveUserId(),
        conversation_id: get().conversationId,
        message: query,
        mode: 'product_focused_analysis',
        target_product_id: productId,
        allow_same_category_comparison: true,
        fast_mode: get().fastMode,
      },
      {
        onToken: (t) => {
          fullText += t
          set({ streamingText: fullText, phase: 'talking' })
        },
        onStatus: (text) => set({ loadingMessage: text }),
        onResult: (r) => {
          resultData = r
        },
        onError: (m) => set({ error: m }),
      },
    )
    set({ _abort: abort })
    await done

    const rd = resultData as Record<string, unknown> | null
    const answer = fullText || (rd?.answer as string) || '抱歉，暂时无法回答您的问题。'
    const convId = (rd?.conversation_id as string) || ''
    const assistantMsg = newMsg('assistant', answer, assistantFromResult(answer, rd))
    set((s) => ({
      isStreaming: false,
      streamingText: '',
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
      set({ conversationId, messages: msgs, error: null })
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
      audioEl = new Audio(url)
      audioEl.onended = () => {
        set({ voicePlaying: false })
        URL.revokeObjectURL(url)
      }
      audioEl.onerror = () => {
        set({ voicePlaying: false })
        URL.revokeObjectURL(url)
      }
      await audioEl.play()
    } catch {
      set({ voicePlaying: false })
    }
  },

  setRecording: (v, seconds = 0) => set({ isRecording: v, recordingSeconds: seconds }),
}))
