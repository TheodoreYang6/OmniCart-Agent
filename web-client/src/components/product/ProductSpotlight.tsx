/**
 * ProductSpotlight — 商品卡聚光展开面板（spec §3.1）。
 *
 * 交互：点击聊天内商品卡不再跳详情页，而是原地放大浮起 + 背景虚化，
 * 从卡片侧边展开版面（桌面左右分栏 / 移动端底部抽屉）。
 * 内容区依次渐入：① 面向用户的选购建议（匹配结论、原因、注意点）
 * ② AI 小总结（流式打字机，结合会话上下文异步生成）。
 */

import { useEffect, useRef, useState } from 'react'
import { X, ExternalLink, ShoppingCart } from 'lucide-react'
import type { DecisionResult, Product } from '@/api/types'
import { api } from '@/api/client'
import { OmiAvatar } from '@/components/brand/Omi'
import { ProductImage } from '@/components/ui/ProductImage'
import { levelStyle } from '@/lib/format'
import { cn, formatPrice } from '@/lib/utils'

interface ProductSpotlightProps {
  product: Product
  decision?: DecisionResult
  /** 用户当轮 query，用于让 AI 总结贴合需求 */
  query?: string
  onClose: () => void
  onOpenDetail: (productId: string) => void
  onAddToCart?: (productId: string) => void
}

export function ProductSpotlight({
  product,
  decision,
  query,
  onClose,
  onOpenDetail,
  onAddToCart,
}: ProductSpotlightProps) {
  const [phase, setPhase] = useState(0) // 0 入场 → 1 建议区 → 2 总结区
  const [summary, setSummary] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  // 分阶段渐入
  useEffect(() => {
    const t1 = setTimeout(() => setPhase(1), 120)
    const t2 = setTimeout(() => setPhase(2), 380)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
    }
  }, [])

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // 异步拉 AI 小总结（流式，走 api/client.ts 统一封装）
  useEffect(() => {
    const ctrl = new AbortController()
    abortRef.current = ctrl
    let acc = ''
    ;(async () => {
      try {
        await api.streamProductSummary(
          product.product_id,
          query ?? '',
          (chunk) => {
            acc += chunk
            setSummary(acc)
            setSummaryLoading(false)
          },
          ctrl.signal,
        )
      } catch {
        if (!acc) setSummary('我先根据已经核对到的商品信息给你一些建议，更细的问题可以随时再问我～')
      } finally {
        setSummaryLoading(false)
      }
    })()
    return () => ctrl.abort()
  }, [product.product_id, query])

  const level = levelStyle(decision?.recommendation_level ?? '')
  const recommendationScore = decision?.recommendation_score
  const image = product.image_urls?.[0]

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
    >
      {/* 背景虚化层（--scrim 随主题：深色下显著加深，让面板真正浮起来）*/}
      <button
        type="button"
        tabIndex={-1}
        aria-label="关闭商品分析"
        className="absolute inset-0 bg-[var(--scrim)] backdrop-blur-md animate-fade-in"
        onClick={onClose}
      />

      {/* 主体：桌面居中左右分栏 / 移动端底部抽屉（上圆角 + 上滑入场） */}
      <div
        className={cn(
          'relative flex w-full flex-col overflow-hidden',
          'max-h-[88vh] rounded-t-3xl animate-slide-up',           // 移动端：底部抽屉
          'sm:max-h-[92vh] sm:max-w-4xl sm:flex-row sm:rounded-3xl sm:animate-scale-in', // 桌面：居中弹窗
          'panel-solid',
        )}
      >
        {/* 移动端抽屉拉手 */}
        <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-ink-muted/40 sm:hidden" />
        <button
          onClick={onClose}
          className="absolute right-3 top-3 z-10 rounded-full bg-[var(--glass-bg-strong)] p-1.5 text-ink-soft transition hover:bg-[var(--surface-variant)] hover:text-ink"
          aria-label="关闭"
        >
          <X size={18} />
        </button>

        {/* 左：放大的商品卡 */}
        <div className="flex shrink-0 flex-col gap-3 p-5 sm:w-[42%]">
          <div className="relative overflow-hidden rounded-2xl bg-[var(--surface-sunken)]">
            <ProductImage
              src={image}
              productId={product.product_id}
              alt={product.title}
              rounded="rounded-none"
              className="aspect-square w-full"
            />
          </div>

          <div className="space-y-1.5">
            {level.label && (
              <span
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium',
                  level.bg,
                  level.text,
                  level.border,
                )}
              >
                <span className={cn('h-1.5 w-1.5 rounded-full', level.dot)} />
                {level.label}
              </span>
            )}
            <p className="text-sm font-semibold leading-snug text-ink">{product.title}</p>
            <p className="text-xs text-ink-muted">
              {product.brand} · {product.sub_category}
            </p>
            <p className="text-xl font-extrabold text-price">{formatPrice(product.price)}</p>
          </div>

          <div className="mt-auto flex gap-2 pt-2">
            {onAddToCart && (
              <button
                onClick={() => onAddToCart(product.product_id)}
                className="btn-primary flex flex-1 items-center justify-center gap-1.5 text-sm"
              >
                <ShoppingCart size={15} /> 加入购物车
              </button>
            )}
            <button
              onClick={() => onOpenDetail(product.product_id)}
              className="flex items-center justify-center gap-1 rounded-xl border border-[var(--field-border)] bg-[var(--glass-bg)] px-3 text-xs text-ink-soft transition hover:border-brand-200 hover:text-brand-600"
            >
              <ExternalLink size={14} /> 完整详情
            </button>
          </div>
        </div>

        {/* 右：选购建议 + AI 总结（依次渐入）*/}
        <div className="min-h-0 flex-1 overflow-y-auto border-t border-[var(--panel-border)] panel-sunken p-5 sm:border-l sm:border-t-0">
          <div
            className={cn(
              'transition-all duration-500',
              phase >= 1 ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
            )}
          >
            {recommendationScore && (
              <div
                className="mb-3 rounded-xl border border-[var(--panel-border)] bg-[var(--panel-bg)] p-3"
                title={recommendationScore.explanation}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-xs font-semibold text-ink">欧米适配指数</span>
                  <span className="text-xl font-extrabold tabular-nums text-brand-700 dark:text-brand-100">
                    {recommendationScore.score}
                    <span className="ml-0.5 text-xs font-medium text-ink-muted">/100</span>
                  </span>
                </div>
                <div
                  className="mt-2 h-2 w-full overflow-hidden rounded-full bg-[var(--surface-variant)]"
                  role="progressbar"
                  aria-valuenow={recommendationScore.score}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="欧米适配指数"
                >
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400 transition-[width] duration-700"
                    style={{ width: `${Math.min(100, Math.max(0, recommendationScore.score ?? 0))}%` }}
                  />
                </div>
                <p className="mt-1.5 text-[11px] leading-snug text-ink-soft">
                  {recommendationScore.match_label} · {recommendationScore.evidence_label}
                </p>
                <div className="mt-2 space-y-1.5">
                  {recommendationScore.dimensions
                    .filter((item) => item.score !== null)
                    .map((item) => (
                      <div key={item.key} className="flex items-center gap-2">
                        <span className="w-16 shrink-0 text-[10px] text-ink-muted">{item.label}</span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-variant)]">
                          <div
                            className="h-full rounded-full bg-brand-500/70 dark:bg-brand-300/70"
                            style={{ width: `${Math.min(100, Math.max(0, item.score ?? 0))}%` }}
                          />
                        </div>
                        <span className="w-8 shrink-0 text-right text-[10px] tabular-nums text-ink-soft">
                          {item.score}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
            <h3 className="mb-3 text-sm font-bold text-ink">选购建议</h3>
            {decision?.why_it_fits && (
              <p className="rounded-xl bg-[var(--panel-bg)] p-2.5 text-xs leading-relaxed text-ink-soft">
                为什么适合：{decision.why_it_fits}
              </p>
            )}
            {decision?.caution && (
              <p className="mt-2 rounded-xl bg-[var(--surface-variant)] p-2.5 text-xs leading-relaxed text-ink-soft">
                购买前留意：{decision.caution}
              </p>
            )}
            <p className="mt-2 text-xs text-ink-muted">
              信息状态：{decision?.evidence_label || '信息有限'}
            </p>

            {(decision?.positive_signal || (decision?.risk_factors?.length ?? 0) > 0) && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {decision?.positive_signal && (
                  <span className="rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                    👍 {decision.positive_signal}
                  </span>
                )}
                {decision?.risk_factors?.map((r, i) => (
                  <span key={i} className="risk-strip rounded-md px-2 py-1 text-[11px]">
                    ⚠ {r}
                  </span>
                ))}
              </div>
            )}

            {decision?.recommendation_reason && (
              <p className="mt-3 rounded-xl bg-[var(--panel-bg)] p-2.5 text-xs leading-relaxed text-ink-soft">
                {decision.recommendation_reason}
              </p>
            )}
          </div>

          {/* 受控商品档案驱动的 LLM 补充解读 */}
          <div
            className={cn(
              'mt-5 transition-all duration-500',
              phase >= 2 ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
            )}
          >
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-bold text-ink">
              <OmiAvatar size={20} expression="happy" />
              欧米的补充分析
            </h3>
            {summaryLoading && !summary ? (
              <div className="flex items-start gap-3">
                <OmiAvatar size={28} phase="thinking" className="shrink-0" />
                <div className="min-w-0 flex-1 space-y-2">
                  <p className="flex items-center gap-1.5 text-xs font-medium text-ink-soft">
                    欧米正在为你总结
                    <span className="ml-0.5 inline-flex gap-0.5" aria-hidden>
                      <span className="h-1 w-1 animate-bounce rounded-full bg-brand-400" />
                      <span className="h-1 w-1 animate-bounce rounded-full bg-brand-400" style={{ animationDelay: '120ms' }} />
                      <span className="h-1 w-1 animate-bounce rounded-full bg-brand-400" style={{ animationDelay: '240ms' }} />
                    </span>
                  </p>
                  <div className="space-y-1.5">
                    <div className="h-2.5 w-full animate-pulse rounded-full bg-[var(--surface-variant)]" />
                    <div className="h-2.5 w-5/6 animate-pulse rounded-full bg-[var(--surface-variant)]" />
                    <div className="h-2.5 w-3/4 animate-pulse rounded-full bg-[var(--surface-variant)]" />
                  </div>
                </div>
              </div>
            ) : (
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">
                {summary}
                {summaryLoading && <span className="ml-0.5 animate-pulse">▍</span>}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
