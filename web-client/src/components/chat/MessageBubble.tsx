import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Volume2, ScanSearch, MapPin, CornerDownRight, Star, Check, AlertTriangle } from 'lucide-react'
import type { ChatMessage } from '@/store/chatStore'
import { ProductCard } from '@/components/product/ProductCard'
import { ProductImage } from '@/components/ui/ProductImage'
import { OmiAppIcon } from '@/components/brand/OmiAppIcon'
import { cn, formatPrice } from '@/lib/utils'
import { ProductComparison } from './ProductComparison'
import { ShopActionCard } from './ShopActionCard'
import type { ChatAction } from '@/api/types'

interface MessageBubbleProps {
  message: ChatMessage
  onProductClick?: (productId: string) => void
  onAddToCart?: (product: { product_id: string }) => void
  onAskAgent?: (productId: string, title: string) => void
  onCompareProduct?: (productId: string, title: string) => void
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
  onCompareProduct,
  onActionClick,
  onOptionClick,
  onPlayTTS,
}: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const hasProducts = message.products.length > 0
  // 单品“问欧米”已有专属聚焦卡；同一件商品再渲染通用 ProductCard 会产生
  // 两张几乎相同的卡片。商品数据仍保留在 message.products 中，供点击展开
  // Spotlight、评分与加购使用，只是不重复展示。
  const showFocusCard = Boolean(message.focusAnalysis && !message.comparison)
  const showProductGrid = hasProducts && !showFocusCard && !message.comparison

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
        {message.text && (
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
        )}

        {message.visualResult && (
          <div className="flex w-fit items-center gap-1.5 rounded-full border border-brand-100 bg-brand-50 px-3 py-1 text-xs text-brand-700 dark:border-brand-500/25 dark:bg-brand-500/10 dark:text-brand-200">
            <ScanSearch size={13} />
            {(() => {
              const visual = message.visualResult ?? {}
              const facts = ['brand', 'product_name', 'product_line', 'model', 'specs', 'category']
                .map((key) => String(visual[key] ?? '').trim())
                .filter(Boolean)
                .filter((value, index, all) => all.indexOf(value) === index)
              return facts.length
                ? `图中识别到：${facts.join(' · ').slice(0, 80)}`
                : String(message.productResolution?.label || '已识别图片中的商品线索，正在按同类为你筛选')
            })()}
          </div>
        )}

        {/* 购物动作结构化卡片（加购 / 规格 / 下单预览 / 下单成功） */}
        {message.shopCard && <ShopActionCard card={message.shopCard} onActionClick={onActionClick} />}

        {/* 横向对比：分栏卡片 + 结论横幅 */}
        {message.comparison && (
          <ProductComparison
            comparison={message.comparison}
            onProductClick={onProductClick ? (id) => onProductClick(id) : undefined}
          />
        )}

        {/* 单品问欧米：聚焦分析卡 */}
        {showFocusCard && message.focusAnalysis && (
          <div className="glass overflow-hidden rounded-2xl">
            <button
              type="button"
              onClick={onProductClick ? () => onProductClick(message.focusAnalysis!.product_id) : undefined}
              aria-label={`查看 ${message.focusAnalysis.title} 的商品详情`}
              className="flex w-full gap-3 p-3 text-left"
            >
              <ProductImage
                src={message.focusAnalysis.image_url}
                productId={message.focusAnalysis.product_id}
                alt={message.focusAnalysis.title}
                className="h-24 w-24 shrink-0"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
                    {message.focusAnalysis.brand}
                  </span>
                  {message.focusAnalysis.rating.avg != null && (
                    <span className="flex items-center gap-1 text-[11px] text-ink-soft">
                      <Star size={11} className="fill-amber-400 text-amber-400" />
                      {message.focusAnalysis.rating.avg}
                      <span className="text-ink-muted">({message.focusAnalysis.rating.count})</span>
                    </span>
                  )}
                </div>
                <p className="mt-1 line-clamp-2 text-sm font-semibold text-ink">{message.focusAnalysis.title}</p>
                <p className="mt-0.5 text-lg font-extrabold text-price">{formatPrice(message.focusAnalysis.price)}</p>
                <p className="mt-0.5 text-[11px] text-ink-muted">适合：{message.focusAnalysis.suitable_for}</p>
              </div>
            </button>
            {message.focusAnalysis.highlights.length > 0 && (
              <div className="flex flex-wrap gap-1 border-t border-[var(--line)] px-3 py-2">
                {message.focusAnalysis.highlights.map((highlight, i) => (
                  <span key={i} className="flex items-center gap-0.5 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                    <Check size={10} />
                    {highlight}
                  </span>
                ))}
              </div>
            )}
            {message.focusAnalysis.cautions.length > 0 && (
              <div className="flex flex-wrap gap-1 px-3 pb-2">
                {message.focusAnalysis.cautions.map((caution, i) => (
                  <span key={i} className="flex items-center gap-0.5 rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                    <AlertTriangle size={10} />
                    {caution}
                  </span>
                ))}
              </div>
            )}
            {onCompareProduct && (
              <div className="border-t border-[var(--line)] p-2">
                <button
                  onClick={() => onCompareProduct(
                    message.focusAnalysis?.product_id ?? '',
                    message.focusAnalysis?.title ?? '',
                  )}
                  className="status-pill w-fit font-medium transition hover:shadow-glow"
                >
                  <ScanSearch size={14} />
                  与同类横向对比
                </button>
              </div>
            )}
          </div>
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
        {showProductGrid && (
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

      </div>
    </div>
  )
}
