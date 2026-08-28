import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Brain, History, ImagePlus, Loader2, MessageCircleHeart, Mic, PenLine, Plus, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { useCartStore } from '@/store/cartStore'
import { useAuthStore } from '@/store/authStore'
import { getEffectiveUserId } from '@/store/authStore'
import { api } from '@/api/client'
import { ChatInput } from '@/components/chat/ChatInput'
import { ConversationHistory } from '@/components/chat/ConversationHistory'
import { ProductSpotlight } from '@/components/product/ProductSpotlight'
import { Modal } from '@/components/ui/Modal'
import { AddressForm } from '@/components/address/AddressForm'
import type { AddressCreateRequest, ChatAction, DecisionResult, Product } from '@/api/types'
import { OmiAppIcon } from '@/components/brand/OmiAppIcon'
import { OmiHero } from '@/components/brand/OmiHero'
import { useOmiState, omiExpressionForMatch } from '@/hooks/useOmiState'
import { toast } from '@/store/toastStore'
import { AGENT_NAME, AGENT_TAGLINE } from '@/config'

const SUGGESTIONS = [
  '推荐一款 2000 元内的降噪蓝牙耳机',
  '适合敏感肌的平价保湿面霜',
  '帮我挑一双适合跑步的运动鞋',
  '有没有适合送礼的高性价比零食',
]

const EMPTY_ADDRESS: AddressCreateRequest = {
  name: '',
  phone: '',
  province: '',
  city: '',
  district: '',
  detail: '',
  is_default: false,
}

const MessageBubble = lazy(() => import('@/components/chat/MessageBubble').then((module) => ({ default: module.MessageBubble })))

/** 流式文本可能刚好停在 Markdown 标记中间；补齐未闭合的粗体标记，避免把 ** 直接露给用户。 */
function renderStreamingMarkdown(text: string) {
  const boldMarkers = (text.match(/(?<!\\)\*\*/g) ?? []).length
  return boldMarkers % 2 === 0 ? text : `${text}**`
}

function statusIconFor(text: string) {
  if (/理解|需求|意图/.test(text)) return Brain
  if (/找|检索|搜索|挑选/.test(text)) return Search
  if (/比对|比较|筛选/.test(text)) return Sparkles
  if (/核对|依据|验证/.test(text)) return ShieldCheck
  return PenLine
}

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
  const setCartQuantity = useCartStore((s) => s.setQuantity)
  const removeCartItem = useCartStore((s) => s.removeItem)
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())
  const setCartContext = useCartStore((s) => s.setContext)
  const sessionId = useChatStore((s) => s.sessionId)

  const [historyOpen, setHistoryOpen] = useState(false)
  const [addressForm, setAddressForm] = useState<AddressCreateRequest>(EMPTY_ADDRESS)
  const [showAddressForm, setShowAddressForm] = useState(false)
  const [savingAddress, setSavingAddress] = useState(false)
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
      if (omiExpressionForMatch(d?.recommendation_level) === 'star') fireOmi('found-good')
      return
    }
    navigate(`/product/${productId}`) // 兑底：消息里找不到则进详情页
  }
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

  const handleAction = async (action: ChatAction) => {
    const type = String(action.type ?? '')
    const label = String(action.label ?? '')
    if (action.route) {
      if (action.route === 'cart') navigate('/cart')
      else if (action.route === 'orders') navigate('/orders')
      else if (action.route === 'address') navigate('/address')
      else navigate(`/${action.route}`)
      return
    }
    if (type === 'address_form') {
      setAddressForm(EMPTY_ADDRESS)
      setShowAddressForm(true)
    } else if (type === 'cart_qty' && action.cart_item_id) {
      const qty = Number(action.quantity ?? 1)
      if (qty >= 1) {
        await setCartQuantity(String(action.cart_item_id), qty)
        toast.success('数量已更新')
      }
    } else if (type === 'cart_remove' && action.cart_item_id) {
      await removeCartItem(String(action.cart_item_id))
      toast.success('已移出购物车')
    } else if (type === 'sku_reselect') {
      toast.info('请在购物车页重新选择规格')
      navigate('/cart')
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

  const saveAddress = async () => {
    if (!addressForm.name.trim() || !addressForm.phone.trim() || !addressForm.detail?.trim()) {
      toast.info('请填写收货人、手机号和详细地址')
      return
    }
    setSavingAddress(true)
    try {
      await api.createAddress(addressForm, getEffectiveUserId())
      toast.success('地址已保存，可以继续下单了')
      setShowAddressForm(false)
    } catch {
      toast.error('地址保存失败')
    } finally {
      setSavingAddress(false)
    }
  }

  const handleAddToCart = async (p: { product_id: string }) => {
    if (!isLoggedIn) {
      toast.info('登录后即可加入购物车')
      navigate('/login', { state: { from: '/chat' } })
      return
    }
    const ok = await addToCart(p.product_id)
    if (ok) {
      fireOmi('added-to-cart')          // 欧米眨眼反馈（1.6s 后自动回落）
      toast.success('已加入购物车')
    }
  }

  const headerTitle = useMemo(() => `${AGENT_NAME} · 购物智能体`, [])

  // 欧米动效：产品状态 → (expression, phase) 统一映射（详见 useOmiState）
  const { visual: omiVisual, fire: fireOmi } = useOmiState({
    phase,
    isStreaming,
    hasStreamingText: !!streamingText,
  })
  const currentStatus = loadingMessage || `${AGENT_NAME}正在思考…`
  const StatusIcon = statusIconFor(currentStatus)

  return (
    <div className="aurora-bg flex h-full flex-col">
      {/* 头部：玻璃条 */}
      <header className="glass-strong z-10 flex items-center gap-3 border-b border-[var(--line)] px-4 py-3">
        <OmiAppIcon size={42} phase={omiVisual.phase} shape="circle" />
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
          aria-label="新对话"
        >
          <Plus size={20} />
        </button>
        <button
          onClick={() => setHistoryOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-muted transition hover:bg-[var(--glass-bg-strong)] hover:text-brand-500"
          title="历史对话"
          aria-label="历史对话"
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
            <Suspense fallback={null}>
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onProductClick={(id) => openSpotlight(id)}
                  onAddToCart={handleAddToCart}
                  onAskAgent={askAgent}
                  onCompareProduct={(id, title) => askAgent(id, title, true)}
                  onActionClick={handleAction}
                  onOptionClick={send}
                  onPlayTTS={playTTS}
                />
              ))}
            </Suspense>

            {/* 流式进行中的助手气泡 */}
            {isStreaming && (
              <div className="flex gap-2.5 animate-fade-in">
                <OmiAppIcon size={38} phase={omiVisual.phase} shape="circle" />
                <div className="flex min-w-0 max-w-[calc(100%-3rem)] flex-col gap-2">
                  <div className="glass w-fit max-w-full rounded-tl-md px-4 py-3">
                    {streamingText ? (
                      <div className="markdown-body typing-cursor">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {renderStreamingMarkdown(streamingText)}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div
                        key={currentStatus}
                        aria-live="polite"
                        className="flex items-center gap-2.5 text-sm text-brand-700 animate-fade-in"
                      >
                        <span className="gradient-brand flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-white shadow-glow">
                          <StatusIcon size={16} aria-hidden="true" />
                        </span>
                        <span>{currentStatus}</span>
                        <Loader2 size={15} className="shrink-0 animate-spin text-brand-500" aria-hidden="true" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            {/* 推荐卡已在 SSE 中锁定，但不抢在回答前打断阅读。先完成实时文字，
                再把同一份受控结果作为完整消息落盘并统一展示。 */}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <ChatInput onSend={send} disabled={isStreaming} />

      <ConversationHistory open={historyOpen} onClose={() => setHistoryOpen(false)} />
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

      {/* 内联收货地址填写 */}
      <Modal open={showAddressForm} onClose={() => setShowAddressForm(false)} title="填写收货地址" variant="bottom">
        <div className="p-5">
          <AddressForm
            value={addressForm}
            onChange={setAddressForm}
            saving={savingAddress}
            onSubmit={saveAddress}
          />
        </div>
      </Modal>
    </div>
  )
}

function WelcomeScreen({ onPick }: { onPick: (text: string) => void }) {
  return (
    // min-h-full（而非 h-full）：内容超高时自然撑开滚动，不会上下被裁切；
    // short: 矮视口紧凑档（MacBook Air 级），外接大屏视觉不变
    <div className="mx-auto flex min-h-full w-full max-w-[960px] flex-col items-center justify-center px-3 py-3 text-center sm:px-6 sm:py-8 short:py-3">
      {/* 欧米和标题各占一行。透明素材保留趴姿，但不再借负边距遮住标题。 */}
      <div className="hero-spotlight relative flex flex-col items-center">
        <div className="absolute inset-x-0 top-0 -z-10 mx-auto h-40 w-40 scale-125 rounded-full bg-brand-200/40 blur-3xl" />
        <OmiHero size="default" className="mb-1" />
        <h1 className="relative z-20 text-2xl font-extrabold sm:text-3xl short:text-xl">
          嗨，我是<span className="gradient-text">{AGENT_NAME}</span> <span aria-hidden>👋</span>
        </h1>
      </div>
      <p className="gradient-text mt-1 text-sm font-semibold">{AGENT_TAGLINE}</p>
      {/* 打字循环行：轮播示例 query，降低“不知道问什么”的冷启动成本 */}
      <p className="mt-2 h-6 text-sm text-ink-soft sm:mt-3 sm:text-[15px] short:mt-1">
        试试问我：<TypeCycle items={SUGGESTIONS} />
      </p>

      {/* 能力入口：Bento 玻璃三卡；矮屏下隐描述收成图标胶囊，省出呼吸空间 */}
      <div className="mt-3 grid w-full max-w-3xl grid-cols-3 gap-1.5 sm:mt-6 sm:gap-2.5 short:mt-2">
        {[
          { icon: MessageCircleHeart, title: '文字对话', desc: '聊需求、比参数、直接下单' },
          { icon: Mic, title: '语音输入', desc: '说一句话，欧米听得懂' },
          { icon: ImagePlus, title: '拍图识物', desc: '截图/实拍，找同款比价' },
        ].map(({ icon: Icon, title, desc }) => (
          <div key={title} className="glass card-hover flex min-w-0 flex-col items-center gap-1 px-1 py-2.5 sm:px-3 sm:py-4 short:py-2">
            <span className="gradient-brand flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow short:h-7 short:w-7">
              <Icon size={17} />
            </span>
            <span className="mt-1 text-[11px] font-semibold text-ink sm:text-[13px] short:mt-0">{title}</span>
            <span className="hidden text-[11px] leading-snug text-ink-muted sm:block short:hidden">{desc}</span>
          </div>
        ))}
      </div>

      <div className="mt-3 grid w-full grid-cols-2 gap-1.5 sm:mt-6 sm:gap-2.5 short:mt-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="glass card-hover group flex min-w-0 items-center gap-1.5 px-2 py-2 text-left text-[11px] text-ink-soft transition hover:text-brand-600 sm:gap-2 sm:px-4 sm:py-3.5 sm:text-sm short:py-2"
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
