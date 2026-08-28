import { useState, type KeyboardEvent, type MouseEvent } from 'react'
import { Plus, Star } from 'lucide-react'
import type { DecisionResult, Product } from '@/api/types'
import { ProductImage } from '@/components/ui/ProductImage'
import { Omi } from '@/components/brand/Omi'
import { formatPrice } from '@/lib/utils'
import { levelStyle } from '@/lib/format'
import { cn } from '@/lib/utils'

interface ProductCardProps {
  product: Product
  decision?: DecisionResult
  variant?: 'grid' | 'chat' | 'feature'
  /** 外部追加类（Bento 跨格等布局类由父层控制） */
  className?: string
  /** 聚光 hover：光斑跟随鼠标（仅 ShopPage 开启，reduced-motion 下 CSS 层自动禁用） */
  spotlightHover?: boolean
  /** 同类横向比较只展示商品事实，不把“是否适合当前需求”的内部决策分当成商品质量。 */
  showDecisionMeta?: boolean
  onClick?: () => void
  onAddToCart?: () => void
  onAskAgent?: () => void
}

export function StarRating({ rating, size = 12 }: { rating: number; size?: number }) {
  const full = Math.round(rating)
  return (
    <span className="inline-flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          size={size}
          className={i < full ? 'fill-amber-400 text-amber-400' : 'fill-[var(--field-border)] text-[var(--field-border)]'}
        />
      ))}
    </span>
  )
}

/** 骨架屏变体（列表加载态） */
export function ProductCardSkeleton() {
  return (
    <div className="card flex flex-col overflow-hidden">
      <div className="shimmer aspect-square w-full bg-[var(--surface-variant)]" />
      <div className="space-y-2 p-3">
        <div className="shimmer h-4 w-full rounded bg-[var(--surface-variant)]" />
        <div className="shimmer h-3 w-2/3 rounded bg-[var(--surface-variant)]" />
        <div className="shimmer h-5 w-1/3 rounded bg-[var(--surface-variant)]" />
      </div>
    </div>
  )
}

/** 商品卡片 — 网格视图 (shop) 与聊天内嵌视图 (chat) 共用。 */
export function ProductCard({
  product,
  decision,
  variant = 'grid',
  className,
  spotlightHover = false,
  showDecisionMeta = true,
  onClick,
  onAddToCart,
  onAskAgent,
}: ProductCardProps) {
  const price = product.price
  const [adding, setAdding] = useState(false)
  const level = decision?.recommendation_level ?? ''
  const ls = levelStyle(level)
  const recommendationScore = decision?.recommendation_score
  const rating = product.avg_rating ?? 0
  const isFeature = variant === 'feature'

  // 聚光 hover：把鼠标位置写入 CSS 变量，光斑由 .spotlight-hover::after 渲染
  const handleSpotMove = spotlightHover
    ? (e: MouseEvent<HTMLDivElement>) => {
        const r = e.currentTarget.getBoundingClientRect()
        e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`)
        e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`)
      }
    : undefined

  return (
    <div
      className={cn(
        'group card card-hover relative flex flex-col overflow-hidden',
        spotlightHover && 'spotlight-hover',
        onClick && 'cursor-pointer',
        className,
      )}
      onClick={onClick}
      onMouseMove={handleSpotMove}
      role={onClick ? 'link' : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? `查看商品：${product.title}` : undefined}
      onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
        if (onClick && event.key === 'Enter') onClick()
      }}
    >
      <div className="relative overflow-hidden">
        <ProductImage
          src={product.image_urls?.[0]}
          productId={product.product_id}
          alt={product.title}
          rounded="rounded-none"
          className="aspect-square w-full transition-transform duration-500 group-hover:scale-105"
        />
        {/* 底部渐变遮罩（hover 浮现） */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-black/10 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        {showDecisionMeta && recommendationScore && (
          <span
            className="absolute left-2 top-2 inline-flex items-baseline gap-1 rounded-md bg-slate-950/78 px-2 py-1 text-white shadow-card backdrop-blur"
            title={recommendationScore.explanation}
          >
            <span className="text-[10px] font-medium text-white/75">欧米指数</span>
            <span className="text-sm font-bold tabular-nums">{recommendationScore.score}</span>
          </span>
        )}
        {/* 指数之外仍保留清晰的匹配结论；数值不代表商品绝对质量。 */}
        {showDecisionMeta && level && (
          // 同样压在恒浅色商品图上：用恒深药丸 + 白字 + 档位色小点，
          // 而不用 levelStyle 的主题色（深色下其半透底会在白图上发淡）
          <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-slate-900/70 px-1.5 py-0.5 text-[10px] font-medium text-white shadow-card backdrop-blur">
            <span className={cn('h-1.5 w-1.5 rounded-full', ls.dot)} />
            {ls.label}
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col p-3">
        <p
          className={cn(
            'line-clamp-2 font-medium leading-snug text-ink',
            isFeature ? 'text-base' : 'text-sm',
          )}
        >
          {product.title}
        </p>
        <div className="mt-1 flex items-center gap-1.5 text-xs text-ink-muted">
          <span className="truncate">{product.brand}</span>
          {!!product.variant_count && (
            <span
              className="shrink-0 rounded-full bg-[var(--surface-variant)] px-1.5 py-px text-[10px] text-ink-muted"
              title="库中还有相似款，已为你合并展示"
            >
              另有 {product.variant_count} 个相似款
            </span>
          )}
          {rating > 0 && (
            <>
              <span>·</span>
              <StarRating rating={rating} />
              <span>{rating.toFixed(1)}</span>
            </>
          )}
        </div>

        {showDecisionMeta && decision?.recommendation_reason && variant === 'chat' && (
          <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-ink-muted">
            {decision.recommendation_reason}
          </p>
        )}

        {showDecisionMeta && recommendationScore && variant === 'chat' && (
          <p className="mt-1.5 line-clamp-1 text-[11px] text-ink-muted" title={recommendationScore.explanation}>
            {recommendationScore.dimensions
              .filter((item) => item.score !== null)
              .slice(0, 3)
              .map((item) => `${item.label} ${item.score}`)
              .join(' · ')}
          </p>
        )}

        {/* Bento 大卡：多露一段商品描述，填满放大后的信息密度 */}
        {isFeature && product.description && (
          <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-ink-muted">
            {product.description}
          </p>
        )}

        {showDecisionMeta && decision?.positive_signal && (
          <p className="mt-1.5 line-clamp-1 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
            👍 {decision.positive_signal}
          </p>
        )}
        {showDecisionMeta && !decision?.positive_signal && decision?.risk_factors && decision.risk_factors.length > 0 && (
          <p className="risk-strip mt-1.5 line-clamp-1 rounded-md px-2 py-1 text-[11px]">
            ⚠ {decision.risk_factors[0]}
          </p>
        )}

        <div className="mt-auto flex items-end justify-between pt-2.5">
          <span className="text-[17px] font-extrabold text-price">{formatPrice(price)}</span>
          <div className="flex items-center gap-1.5">
            {onAskAgent && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onAskAgent()
                }}
                className="flex items-center gap-1 rounded-lg border border-brand-200 bg-[var(--glass-bg)] px-2 py-1.5 text-xs font-medium text-brand-600 backdrop-blur transition hover:bg-brand-500/10 hover:shadow-glow"
                title="问欧米"
                aria-label={`问欧米关于 ${product.title}`}
              >
                <Omi size={16} /> 问欧米
              </button>
            )}
            {onAddToCart && (
              <button
                onClick={async (e) => {
                  e.stopPropagation()
                  if (adding) return
                  setAdding(true)
                  try { await onAddToCart() } finally { setAdding(false) }
                }}
                disabled={adding}
                className="gradient-brand flex h-8 w-8 items-center justify-center rounded-full text-white shadow-glow transition hover:shadow-glow-lg active:scale-90"
                title="加入购物车"
                aria-label={`将 ${product.title} 加入购物车`}
              >
                <Plus size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
