import { AlertTriangle, Check, CircleCheck, Sparkles, Star } from 'lucide-react'
import type { Comparison, ComparisonItem } from '@/api/types'
import { OmiAvatar } from '@/components/brand/Omi'
import { ProductImage } from '@/components/ui/ProductImage'
import { cn, formatPrice } from '@/lib/utils'

interface ProductComparisonProps {
  comparison: Comparison
  onProductClick?: (productId: string) => void
}

export function ProductComparison({ comparison, onProductClick }: ProductComparisonProps) {
  const { dimensions, target, alternatives, verdict } = comparison
  const items = [target, ...alternatives]
  const winnerId = verdict.winner_id

  return (
    <div className="space-y-3">
      <div className="gradient-brand relative overflow-hidden rounded-2xl p-3.5 text-white shadow-glow">
        <div className="flex items-start gap-2.5">
          <OmiAvatar size={30} expression="happy" className="shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-snug">{verdict.text}</p>
            {verdict.reasons.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {verdict.reasons.map((reason, i) => (
                  <span key={i} className="rounded-full bg-white/15 px-2 py-0.5 text-[11px]">
                    {reason}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
        {comparison.selection_method && (
          <p className="mt-2 pl-[42px] text-[11px] leading-relaxed text-white/72">
            已按同类范围、价格差异与可核对资料筛选
          </p>
        )}
      </div>

      <div className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2">
        {items.map((item, index) => (
          <ComparisonCard
            key={item.product_id}
            item={item}
            dimensions={dimensions}
            isWinner={item.product_id === winnerId}
            index={index}
            onClick={onProductClick ? () => onProductClick(item.product_id) : undefined}
          />
        ))}
      </div>
    </div>
  )
}

function ComparisonCard({
  item,
  dimensions,
  isWinner,
  index,
  onClick,
}: {
  item: ComparisonItem
  dimensions: string[]
  isWinner: boolean
  index: number
  onClick?: () => void
}) {
  const rating = item.rating
  const hasPriceRange = item.price_range.min !== item.price_range.max

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => {
        if (onClick && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault()
          onClick()
        }
      }}
      aria-label={`查看 ${item.title} 的商品详情`}
      className={cn(
        'glass w-[248px] shrink-0 cursor-pointer snap-start overflow-hidden rounded-2xl animate-slide-up transition-all duration-300 hover:-translate-y-1 hover:shadow-float',
        isWinner && 'ring-2 ring-brand-400/60 shadow-glow',
      )}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="relative overflow-hidden">
        <ProductImage
          src={item.image_url}
          productId={item.product_id}
          alt={item.title}
          rounded="rounded-none"
          className="aspect-square w-full"
        />
        {isWinner && (
          <span className="absolute left-2 top-2 flex items-center gap-0.5 rounded-full bg-brand-500 px-2 py-0.5 text-[10px] font-semibold text-white shadow-glow">
            <Sparkles size={10} />
            欧米推荐
          </span>
        )}
      </div>

      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
            {item.brand}
          </span>
          {rating.avg != null && (
            <span className="flex items-center gap-1 text-[11px] text-ink-soft">
              <Star size={11} className="fill-amber-400 text-amber-400" />
              {rating.avg}
              <span className="text-ink-muted">({rating.count})</span>
            </span>
          )}
        </div>

        {(item.comparison_role || item.price_band) && (
          <div className="flex flex-wrap gap-1">
            {item.comparison_role && (
              <span className="rounded-md bg-[var(--surface-variant)] px-1.5 py-0.5 text-[10px] font-medium text-ink-soft">
                {item.comparison_role}
              </span>
            )}
            {item.price_band && (
              <span className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
                {item.price_band}
              </span>
            )}
          </div>
        )}

        <p className="line-clamp-2 text-sm font-semibold leading-snug text-ink">{item.title}</p>

        <div>
          <p className="text-lg font-extrabold text-price">{formatPrice(item.price)}</p>
          {hasPriceRange && (
            <p className="text-[11px] text-ink-muted">
              区间 {formatPrice(item.price_range.min)} - {formatPrice(item.price_range.max)}
            </p>
          )}
        </div>

        <div className="space-y-1 rounded-xl bg-surface-soft/65 px-2 py-1.5">
          {dimensions.map((dim) => (
            <div key={dim} className="flex items-center justify-between gap-2 text-[11px]">
              <span className="shrink-0 text-ink-muted">{dim}</span>
              <span className="truncate text-right font-medium text-ink-soft">
                {item.attributes[dim] ?? '—'}
              </span>
            </div>
          ))}
        </div>

        {item.highlights.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {item.highlights.map((highlight, i) => (
              <span
                key={i}
                className="flex items-center gap-0.5 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
              >
                <Check size={10} />
                {highlight}
              </span>
            ))}
          </div>
        )}

        {item.cautions.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {item.cautions.map((caution, i) => (
              <span
                key={i}
                className="flex items-center gap-0.5 rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
              >
                <AlertTriangle size={10} />
                {caution}
              </span>
            ))}
          </div>
        )}

        <p className="border-t border-[var(--line)] pt-2 text-[11px] leading-relaxed text-ink-soft">
          <span className="inline-flex items-center gap-1 font-medium text-ink">
            <CircleCheck size={12} className="text-brand-500" /> 怎么选
          </span>
          <span className="ml-1">{item.suitable_for}</span>
        </p>
      </div>
    </div>
  )
}
