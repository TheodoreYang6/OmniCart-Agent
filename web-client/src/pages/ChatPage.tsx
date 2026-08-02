import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { History, Plus, Sparkles, Mic, ImagePlus, MessageCircleHeart } from 'lucide-react'
import { useChatStore, type ChatMessage } from '@/store/chatStore'
import { useCartStore } from '@/store/cartStore'
import { MessageBubble } from '@/components/chat/MessageBubble'
import { ChatInput } from '@/components/chat/ChatInput'
import { ConversationHistory } from '@/components/chat/ConversationHistory'
import { AgentInsights, type InsightData } from '@/components/chat/AgentInsights'
import { ProductSpotlight } from '@/components/product/ProductSpotlight'
import type { DecisionResult, Product } from '@/api/types'
import { Modal } from '@/components/ui/Modal'
import { OmiAvatar } from '@/components/brand/Omi'
import { OmiPerch } from '@/components/brand/OmiPerch'
import { AgentTrail } from '@/components/chat/AgentTrail'
import { useOmiState, omiExpressionForScore } from '@/hooks/useOmiState'
import { toast } from '@/store/toastStore'
import { AGENT_NAME, AGENT_TAGLINE } from '@/config'

const SUGGESTIONS = [
  '推荐一款 2000 元内的降噪蓝牙耳机',
  '适合敏感肌的平价保湿面霜',
  '帮我挑一双适合跑步的运动鞋',
  '有没有适合送礼的高性价比零食',
]

export function ChatPage() {
  const navigate = useNavigate()
  const messages = useChatStore((s) => s.messages)
  const streamingText = useChatStore((s) => s.streamingText)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const phase = useChatStore((s) => s.phase)
  const loadingMessage = useChatStore((s) => s.loadingMessage)
  const error = useChatStore((s) => s.error)
  const conversationId = useChatStore((s) => s.conversationId)
  const send = useChatStore((s) => s.send)
  const askAgent = useChatStore((s) => s.askAgent)
  const playTTS = useChatStore((s) => s.playTTS)
  const newConversation = useChatStore((s) => s.newConversation)
  const clearError = useChatStore((s) => s.clearError)
  const setChatScrollTop = useChatStore((s) => s.setChatScrollTop)

  const addToCart = useCartStore((s) => s.addToCart)
  const setCartContext = useCartStore((s) => s.setContext)
  const sessionId = useChatStore((s) => s.sessionId)

  const [historyOpen, setHistoryOpen] = useState(false)
  const [insight, setInsight] = useState<InsightData | null>(null)
  // Spotlight：点击聊天内商品卡原地展开评分细则 + AI 总结（不再跳详情页）
  const [spotlight, setSpotlight] = useState<{
    product: Product
    decision?: DecisionResult
    query?: string
  } | null>(null)

  /** 从消息历史里定位商品与其决策结果，并带上该轮的用户 query（供 AI 总结贴合需求） */
  const openSpotlight = (productId: string) => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i]
      const p = m.products?.find((x) => x.product_id === productId)
      if (!p) continue
      const d = m.decisionResults?.find((x) => x.product_id === productId)
      // 往上找最近的用户提问作为需求上下文
      let q = ''
      for (let j = i; j >= 0; j--) {
        if (messages[j].role === 'user') {
          q = messages[j].text
          break
        }
      }
      setSpotlight({ product: p, decision: d, query: q })
      // 场景②：浏览商品卡 —— 高分好物才给星星眼（避免滥用失去意义）
      if (omiExpressionForScore(d?.display_score) === 'star') fireOmi('found-good')
      return
    }
    navigate(`/product/${productId}`) // 兑底：消息里找不到则进详情页
  }
  // 思考-行动轨迹（纯视图层累计 loadingMessage 历史，深度思考时展示时间线）
  const [statusTrail, setStatusTrail] = useState<string[]>([])

  useEffect(() => {
    if (!isStreaming) {
      setStatusTrail([])
      return
    }
    if (loadingMessage) {
      setStatusTrail((prev) =>
        prev[prev.length - 1] === loadingMessage ? prev : [...prev.slice(-4), loadingMessage],
      )
    }
  }, [loadingMessage, isStreaming])

  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // 同步购物车上下文，保证对话式加购归属正确
  useEffect(() => {
    setCartContext(sessionId, conversationId)
  }, [sessionId, conversationId, setCartContext])

  // 自动滚底：仅在"新消息产生"或"流式进行中"时触发——从详情页返回重挂载时
  // messages 数量未变，不再强制拉底（用户反馈：应停留在离开前的位置）
  const prevCountRef = useRef(-1)
  useEffect(() => {
    const grew = messages.length > prevCountRef.current && prevCountRef.current !== -1
    const firstMount = prevCountRef.current === -1
    prevCountRef.current = messages.length
    if (firstMount) {
      // 首次挂载：有保存位置→恢复（instant）；无→滚底（首次进入/新会话）。
      // 用 rAF 延到布局完成后执行，否则此时列表高度不足 scrollTop 会被镐回 0
      const saved = useChatStore.getState().chatScrollTop
      requestAnimationFrame(() => {
        if (saved !== null && saved > 0 && scrollRef.current) {
          scrollRef.current.scrollTop = saved
        } else {
          bottomRef.current?.scrollIntoView()
        }
      })
      return
    }
    if (grew || isStreaming) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, streamingText, isStreaming])

  // 实时记录滚动位置（不能放到 unmount cleanup：React 那时已置空 ref，
  // 实拍坐实保到的是 null 导致回退到滚底）
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    // 流式中的自动滚动不记录，避免把"自动拉到底"当成用户意图
    if (isStreaming) return
    setChatScrollTop(el.scrollTop)
  }

  useEffect(() => {
    if (error) {
      toast.error(error)
      clearError()
    }
  }, [error, clearError])

  const isEmpty = messages.length === 0

  const handleAction = async (action: Record<string, unknown>) => {
    const type = String(action.type ?? '')
    const label = String(action.label ?? '')
    if (type === 'address_form') {
      navigate('/address')
    } else if (type === 'sku_option' && action.product_id) {
      // 规格按钮带 product_id → 直连加购 API，省掉一轮 LLM 往返
      const skuId = action.sku_id ? String(action.sku_id) : null
      const ok = await addToCart(String(action.product_id), skuId)
      if (ok) fireOmi('added-to-cart')   // 欧米眨眼反馈
      toast[ok ? 'success' : 'error'](ok ? `已加入购物车（${label}）` : '加购失败')
    } else if (type === 'quick_reply' || type === 'sku_option') {
      send(label)
    }
  }

  const handleAddToCart = async (p: { product_id: string }) => {
    const ok = await addToCart(p.product_id)
    if (ok) {
      fireOmi('added-to-cart')          // 欧米眨眼反馈（1.6s 后自动回落）
      toast.success('已加入购物车')
    }
  }

  const openInsights = (m: ChatMessage) => {
    setInsight({
      products: m.products,
      decisionResults: m.decisionResults,
      evidenceList: m.evidenceList,
      traceSteps: m.traceSteps,
      retrievalPlan: m.retrievalPlan,
      sufficiencyReport: m.sufficiencyReport,
      constraints: m.constraints,
      harnessReport: m.harnessReport,
    })
  }

  const headerTitle = useMemo(() => `${AGENT_NAME} · 购物智能体`, [])

  // 欧米动效：产品状态 → (expression, phase) 统一映射（详见 useOmiState）
  const { visual: omiVisual, fire: fireOmi } = useOmiState({
    phase,
    isStreaming,
    hasStreamingText: !!streamingText,
  })

  return (
    <div className="aurora-bg flex h-full flex-col">
      {/* 头部：玻璃条 */}
      <header className="glass-strong z-10 flex items-center gap-3 border-b border-[var(--line)] px-4 py-3">
        <OmiAvatar size={32} {...omiVisual} />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-bold leading-tight text-ink">{headerTitle}</p>
          <p className="text-xs text-ink-muted">
            {isStreaming ? '正在思考…' : '陪你聊着买 · 探索未来购物新范式'}
          </p>
        </div>
        <button
          onClick={() => newConversation()}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-muted transition hover:bg-[var(--glass-bg-strong)] hover:text-brand-500"
          title="新对话"
        >
          <Plus size={20} />
        </button>
        <button
          onClick={() => setHistoryOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-muted transition hover:bg-[var(--glass-bg-strong)] hover:text-brand-500"
          title="历史对话"
        >
          <History size={20} />
        </button>
      </header>

      {/* 消息区 */}
      <div ref={scrollRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-y-auto">
        {isEmpty && !isStreaming ? (
          <WelcomeScreen onPick={(t) => send(t)} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-5 px-3 py-5 sm:px-4">
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                onProductClick={(id) => openSpotlight(id)}
                onAddToCart={handleAddToCart}
                onAskAgent={askAgent}
                onOpenInsights={openInsights}
                onActionClick={handleAction}
                onOptionClick={send}
                onPlayTTS={playTTS}
              />
            ))}

            {/* 流式进行中的助手气泡 */}
            {isStreaming && (
              <div className="flex gap-2.5 animate-fade-in">
                <OmiAvatar size={28} {...omiVisual} />
                <div className="flex min-w-0 max-w-[calc(100%-3rem)] flex-col gap-2">
                  {/* 思考-行动轨迹（P2 卡片流：完成步打勾、当前步 spinner+光环） */}
                  {!streamingText && statusTrail.length > 1 && (
                    <AgentTrail steps={statusTrail} />
                  )}
                  <div className="glass w-fit max-w-full rounded-tl-md px-4 py-3">
                    {streamingText ? (
                      <p className="markdown-body whitespace-pre-wrap typing-cursor">
                        {streamingText}
                      </p>
                    ) : (
                      <div className="flex items-center gap-2.5 text-sm text-brand-700">
                        <span className="flex gap-1">
                          <span className="dot-bounce" />
                          <span className="dot-bounce" />
                          <span className="dot-bounce" />
                        </span>
                        {loadingMessage || `${AGENT_NAME}正在思考…`}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <ChatInput onSend={send} disabled={isStreaming} />

      <ConversationHistory open={historyOpen} onClose={() => setHistoryOpen(false)} />
      <Modal
        open={!!insight}
        onClose={() => setInsight(null)}
        title={`${AGENT_NAME}的推理过程`}
        variant="bottom"
        className="sm:max-w-2xl"
      >
        <div className="h-[70vh]">{insight && <AgentInsights data={insight} />}</div>
      </Modal>

      {spotlight && (
        <ProductSpotlight
          product={spotlight.product}
          decision={spotlight.decision}
          query={spotlight.query}
          onClose={() => setSpotlight(null)}
          onOpenDetail={(id) => {
            setSpotlight(null)
            navigate(`/product/${id}`)
          }}
          onAddToCart={(id) => handleAddToCart({ product_id: id })}
        />
      )}
    </div>
  )
}

function WelcomeScreen({ onPick }: { onPick: (text: string) => void }) {
  return (
    // min-h-full（而非 h-full）：内容超高时自然撑开滚动，不会上下被裁切；
    // short: 矮视口紧凑档（MacBook Air 级），外接大屏视觉不变
    <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center px-6 py-8 text-center short:py-5">
      {/* P1 影院化主视觉：欧米卧在主标题上（前爪压住字的上沿）+ 顶部聚光锥。
          -mb 负边距造重叠（而非 absolute）：保持在文档流内，标题不会因脉出而跳位 */}
      <div className="hero-spotlight relative flex flex-col items-center">
        <div className="absolute inset-x-0 top-0 -z-10 mx-auto h-40 w-40 scale-125 rounded-full bg-brand-200/40 blur-3xl" />
        <OmiPerch className="-mb-5 w-56 cursor-pointer sm:w-64 short:-mb-4 short:w-44" />
        <h1 className="text-2xl font-extrabold sm:text-3xl short:text-xl">
          嗨，我是<span className="gradient-text">{AGENT_NAME}</span> <span>👋</span>
        </h1>
      </div>
      <p className="gradient-text mt-1 text-sm font-semibold">{AGENT_TAGLINE}</p>
      {/* 打字循环行：轮播示例 query，降低“不知道问什么”的冷启动成本 */}
      <p className="mt-3 h-6 text-[15px] text-ink-soft short:mt-2">
        试试问我：<TypeCycle items={SUGGESTIONS} />
      </p>

      {/* 能力入口：Bento 玻璃三卡；矮屏下隐描述收成图标胶囊，省出呼吸空间 */}
      <div className="mt-6 grid w-full max-w-xl grid-cols-1 gap-2.5 sm:grid-cols-3 short:mt-4">
        {[
          { icon: MessageCircleHeart, title: '文字对话', desc: '聊需求、比参数、直接下单' },
          { icon: Mic, title: '语音输入', desc: '说一句话，欧米听得懂' },
          { icon: ImagePlus, title: '拍图识物', desc: '截图/实拍，找同款比价' },
        ].map(({ icon: Icon, title, desc }) => (
          <div key={title} className="glass card-hover flex flex-col items-center gap-1 px-3 py-4 short:flex-row short:justify-center short:gap-2 short:py-2.5">
            <span className="gradient-brand flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow short:h-7 short:w-7">
              <Icon size={17} />
            </span>
            <span className="mt-1 text-[13px] font-semibold text-ink short:mt-0">{title}</span>
            <span className="text-[11px] leading-snug text-ink-muted short:hidden">{desc}</span>
          </div>
        ))}
      </div>

      <div className="mt-6 grid w-full gap-2.5 sm:grid-cols-2 short:mt-4">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="glass card-hover group flex items-center gap-2 px-4 py-3.5 text-left text-sm text-ink-soft transition hover:text-brand-600 short:py-2.5"
          >
            <Sparkles size={15} className="shrink-0 text-brand-400 transition-transform duration-200 group-hover:scale-125 group-hover:rotate-12" />
            <span className="line-clamp-1">{s}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/** 打字循环：逐字打出→停留→删除→下一条；reduced-motion 下静态展示首条 */
function TypeCycle({ items }: { items: string[] }) {
  const reduced = useMemo(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )
  const [idx, setIdx] = useState(0)
  const [len, setLen] = useState(0)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (reduced) return
    const text = items[idx]
    let t: number
    if (!deleting) {
      if (len < text.length) t = window.setTimeout(() => setLen(len + 1), 55)
      else t = window.setTimeout(() => setDeleting(true), 1800)
    } else {
      if (len > 0) t = window.setTimeout(() => setLen(len - 1), 22)
      else {
        setDeleting(false)
        setIdx((idx + 1) % items.length)
        t = window.setTimeout(() => {}, 0)
      }
    }
    return () => clearTimeout(t)
  }, [len, deleting, idx, items, reduced])

  return (
    <span className="typing-cursor font-medium text-brand-600">
      {reduced ? items[0] : items[idx].slice(0, len)}
    </span>
  )
}
