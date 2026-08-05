import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Volume2, ScanSearch, MapPin, CornerDownRight } from 'lucide-react'
import type { ChatMessage } from '@/store/chatStore'
import { ProductCard } from '@/components/product/ProductCard'
import { OmiAppIcon } from '@/components/brand/OmiAppIcon'
import { AGENT_NAME } from '@/config'
import { cn } from '@/lib/utils'
import { ComparisonTable } from './ComparisonTable'
import { TrailSummary } from './AgentTrail'
import { EvidenceStrip } from './EvidenceStrip'
import type { ChatAction } from '@/api/types'

interface MessageBubbleProps {
  message: ChatMessage
  onProductClick?: (productId: string) => void
  onAddToCart?: (product: { product_id: string }) => void
  onAskAgent?: (productId: string, title: string) => void
  onOpenInsights?: (message: ChatMessage) => void
  onActionClick?: (action: ChatAction) => void
  onOptionClick?: (text: string) => void
  onPlayTTS?: (text: string) => void
}

const AgentAvatar = () => <OmiAppIcon size={38} shape="circle" />

export function MessageBubble({
  message,
  onProductClick,
  onAddToCart,
  onAskAgent,
  onOpenInsights,
  onActionClick,
  onOptionClick,
  onPlayTTS,
}: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const hasProducts = message.products.length > 0
  const hasInsights =
    message.traceSteps.length > 0 ||
    message.decisionResults.length > 0 ||
    message.evidenceList.length > 0

  const decisionMap = useMemo(() => {
    const m = new Map<string, (typeof message.decisionResults)[number]>()
    message.decisionResults.forEach((d) => m.set(d.product_id, d))
    return m
  }, [message])

  // Preserve every ranked result; layout must adapt instead of discarding relevant products.
  const displayProducts = message.products

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="flex max-w-[85%] flex-col items-end gap-2 sm:max-w-[70%]">
          {message.imageUrl && (
            <img
              src={message.imageUrl}
              alt="上传图片"
              className="max-h-52 rounded-2xl rounded-br-md border border-[var(--line)] object-cover shadow-lift"
            />
          )}
          {message.text && (
            <div className="gradient-brand rounded-2xl rounded-br-md px-4 py-2.5 text-[15px] leading-relaxed text-white shadow-float">
              {message.isVoice && <span className="mr-1 opacity-80">🎙</span>}
              {message.text}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-2.5 animate-slide-up">
      <AgentAvatar />
      <div className="flex min-w-0 max-w-[calc(100%-3rem)] flex-1 flex-col gap-2.5">
        <div className="glass w-fit max-w-full rounded-tl-md px-4 py-3">
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
          </div>
          {message.status === 'stopped' && <p className="mt-2 text-xs text-ink-muted">已停止生成</p>}
          {onPlayTTS && message.text.length > 4 && (
            <button
              onClick={() => onPlayTTS(message.text)}
              className="mt-2 flex items-center gap-1 text-xs text-ink-muted transition hover:text-brand-500"
              aria-label="朗读欧米的回答"
            >
              <Volume2 size={13} /> 朗读
            </button>
          )}
        </div>

        {/* 聚焦分析对比表 */}
        {message.comparisonTable && (
          <ComparisonTable
            table={message.comparisonTable}
            analysis={message.targetProductAnalysis}
          />
        )}

        {/* 澄清选项 */}
        {message.clarificationOptions && message.clarificationOptions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {message.clarificationOptions.map((opt, i) => {
              const label = String(opt.label ?? opt.value ?? '')
              if (!label) return null
              return (
                <button key={i} className="chip" onClick={() => onOptionClick?.(String(opt.value ?? label))}>
                  {label}
                </button>
              )
            })}
          </div>
        )}

        {/* 购物操作按钮 (下单确认 / 地址表单 / SKU 选择) */}
        {message.actions && message.actions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {message.actions.map((act, i) => {
              const type = String(act.type ?? '')
              const label = String(act.label ?? '')
              if (!label) return null
              const isAddr = type === 'address_form'
              return (
                <button
                  key={i}
                  onClick={() => onActionClick?.(act)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition active:scale-95',
                    isAddr
                      ? 'border border-brand-200 bg-[var(--glass-bg-strong)] text-brand-600 backdrop-blur hover:bg-brand-500/10'
                      : 'gradient-brand text-white shadow-glow hover:brightness-105',
                  )}
                >
                  {isAddr ? <MapPin size={15} /> : <CornerDownRight size={15} />}
                  {label}
                </button>
              )
            })}
          </div>
        )}

        {/* 商品结果 */}
        {hasProducts && (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            {displayProducts.map((p) => (
              <ProductCard
                key={p.product_id}
                product={p}
                decision={decisionMap.get(p.product_id)}
                variant="chat"
                onClick={() => onProductClick?.(p.product_id)}
                onAddToCart={onAddToCart ? () => onAddToCart({ product_id: p.product_id }) : undefined}
                onAskAgent={onAskAgent ? () => onAskAgent(p.product_id, p.title) : undefined}
              />
            ))}
          </div>
        )}

        {/* 备选商品 (聚焦分析) */}
        {message.alternativeProducts && message.alternativeProducts.length > 0 && !hasProducts && (
          <div className="flex flex-wrap gap-2">
            {message.alternativeProducts.map((a, i) => (
              <button
                key={i}
                onClick={() => onProductClick?.(String(a.product_id ?? ''))}
                className="glass card-hover flex items-center gap-2 rounded-xl px-3 py-2 text-left"
              >
                <div className="min-w-0">
                  <p className="line-clamp-1 text-xs font-medium text-ink">{String(a.title ?? '')}</p>
                  <p className="text-xs text-price">
                    ¥{Number(a.price ?? 0).toFixed(0)} · {String(a.recommendation_level ?? '')}
                  </p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* 推理轨迹回看 + 证据外显 + 完整推理面板入口（P2/P3 一等公民区） */}
        {(message.traceSteps.length > 0 || message.evidenceList.length > 0 || hasInsights) && (
          <div className="flex flex-wrap items-start gap-2">
            <TrailSummary steps={message.traceSteps} />
            <EvidenceStrip items={message.evidenceList} />
            {hasInsights && (
              <button
                onClick={() => onOpenInsights?.(message)}
                className="status-pill w-fit font-medium transition hover:shadow-glow"
              >
                <ScanSearch size={14} />
                查看{AGENT_NAME}的推理过程
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
