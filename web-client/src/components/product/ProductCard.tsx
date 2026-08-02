import type { MouseEvent } from 'react'
import { Plus, Star } from 'lucide-react'
import type { DecisionResult, Product } from '@/api/types'
import { ProductImage } from '@/components/ui/ProductImage'
import { Omi } from '@/components/brand/Omi'
import { formatPrice } from '@/lib/utils'
import { levelStyle, scoreColorOnScrim } from '@/lib/format'
import { cn } from '@/lib/utils'

interface ProductCardProps {
  product: Product
  decision?: DecisionResult
  variant?: 'grid' | 'chat' | 'feature'
  /** 外部追加类（Bento 跨格等布局类由父层控制） */
  className?: string
  /** 聚光 hover：光斑跟随鼠标（仅 ShopPage 开启，reduced-motion 下 CSS 层自动禁用） */
  spotlightHover?: boolean
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

/** 决策分环形进度（SVG stroke-dasharray，零依赖） */
/** 置信度环配色（P3）：按推荐档位给色，一眼区分“多确信” */
const RING_COLORS: Record<string, [string, string]> = {
  strong_recommend: ['#10B981', '#34D399'], // emerald — 强推
  recommended: ['#256BFF', '#38BDF8'], // brand — 推荐
  worth_considering: ['#0EA5E9', '#7DD3FC'], // sky — 值得考虑
  cautious: ['#94A3B8', '#CBD5E1'], // slate — 谨慎
}

function ScoreRing({ score, level }: { score: number; level?: string }) {
  const pct = Math.max(0, Math.min(1, score / 10))
  const r = 9
  const c = 2 * Math.PI * r
  const [c1, c2] = RING_COLORS[level ?? ''] ?? RING_COLORS.recommended
  const gid = `sg-${(level ?? 'recommended').replace(/[^a-z_]/g, '')}`
  return (
    <span className="relative inline-flex h-7 w-7 items-center justify-center">
      <svg width="28" height="28" viewBox="0 0 28 28" className="-rotate-90">
        <circle cx="14" cy="14" r={r} fill="none" stroke="rgba(255,255,255,0.28)" strokeWidth="3" />
        <circle
          cx="14" cy="14" r={r} fill="none"
          stroke={`url(#${gid})`} strokeWidth="3" strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`}
        />
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={c1} />
            <stop offset="1" stopColor={c2} />
          </linearGradient>
        </defs>
      </svg>
      <span className={cn('absolute text-[9px] font-bold', scoreColorOnScrim(score))}>
        {score.toFixed(1)}
      </span>
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
  onClick,
  onAddToCart,
  onAskAgent,
}: ProductCardProps) {
  const price = decision ? product.price : product.price
  const score = decision?.display_score ?? 0
  const level = decision?.recommendation_level ?? ''
  const ls = levelStyle(level)
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
    >
      <div className="relative overflow-hidden">
        <ProductImage
          src={product.image_urls?.[0]}
          alt={product.title}
          rounded="rounded-none"
          className="aspect-square w-full transition-transform duration-500 group-hover:scale-105"
        />
        {/* 底部渐变遮罩（hover 浮现） */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-black/10 to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
        {decision && score > 0 && (
          // 恒深药丸：角标压在恒浅色商品图上，不能跟主题翻转
          <div className="absolute left-2 top-2 rounded-full bg-slate-900/70 p-0.5 shadow-card backdrop-blur">
            <ScoreRing score={score} level={level} />
          </div>
        )}
        {level && (
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

        {decision?.recommendation_reason && variant === 'chat' && (
          <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-ink-muted">
            {decision.recommendation_reason}
          </p>
        )}

        {/* Bento 大卡：多露一段商品描述，填满放大后的信息密度 */}
        {isFeature && product.description && (
          <p className="mt-1.5 line-clamp-2 text-xs leading-snug text-ink-muted">
            {product.description}
          </p>
        )}

        {decision?.positive_signal && (
          <p className="mt-1.5 line-clamp-1 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
            👍 {decision.positive_signal}
          </p>
        )}
        {!decision?.positive_signal && decision?.risk_factors && decision.risk_factors.length > 0 && (
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
              >
                <Omi size={16} /> 问欧米
              </button>
            )}
            {onAddToCart && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onAddToCart()
                }}
                className="gradient-brand flex h-8 w-8 items-center justify-center rounded-full text-white shadow-glow transition hover:shadow-glow-lg active:scale-90"
                title="加入购物车"
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
