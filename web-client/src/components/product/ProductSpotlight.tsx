/**
 * ProductSpotlight — 商品卡聚光展开面板（spec §3.1）。
 *
 * 交互：点击聊天内商品卡不再跳详情页，而是原地放大浮起 + 背景虚化，
 * 从卡片侧边展开版面（桌面左右分栏 / 移动端底部抽屉）。
 * 内容区依次渐入：① 评分细则（校准分 + 标签 + 各维度条 + 好评率/风险）
 * ② AI 小总结（流式打字机，结合会话上下文异步生成）。
 */

import { useEffect, useRef, useState } from 'react'
import { X, ExternalLink, ShoppingCart, Loader2 } from 'lucide-react'
import type { DecisionResult, Product } from '@/api/types'
import { api } from '@/api/client'
import { OmiAvatar } from '@/components/brand/Omi'
import { omiExpressionForScore } from '@/hooks/useOmiState'
import { resolveImageUrl } from '@/config'
import { COMPONENT_LABELS, componentLabel, levelStyle, scoreColor, scoreColorOnScrim } from '@/lib/format'
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

/** 单个维度评分条 */
function ScoreBar({ label, score, weight }: { label: string; score: number; weight?: number }) {
  const pct = Math.max(0, Math.min(100, score * 100))
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-ink-soft">
          {label}
          {weight ? <span className="ml-1 text-[10px] text-ink-muted">权重 {Math.round(weight * 100)}%</span> : null}
        </span>
        <span className={cn('font-semibold tabular-nums', scoreColor(score * 10))}>
          {(score * 10).toFixed(1)}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full meter-track">
        <div
          className="h-full rounded-full gradient-brand transition-all duration-700 ease-out dark:shadow-[0_0_6px_rgba(77,139,255,0.55)]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function ProductSpotlight({
  product,
  decision,
  query,
  onClose,
  onOpenDetail,
  onAddToCart,
}: ProductSpotlightProps) {
  const [phase, setPhase] = useState(0) // 0 入场 → 1 评分区 → 2 总结区
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
        if (!acc) setSummary('欧米暂时没法生成总结，可以先看看下面的评分细则～')
      } finally {
        setSummaryLoading(false)
      }
    })()
    return () => ctrl.abort()
  }, [product.product_id, query])

  const score = decision?.display_score ?? 0
  const level = levelStyle(decision?.recommendation_level ?? '')
  const comps = Object.entries(decision?.component_scores ?? {}).filter(
    ([k, v]) => v && typeof v.score === 'number' && k in COMPONENT_LABELS,
  )
  const image = product.image_urls?.[0]

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
    >
      {/* 背景虚化层（--scrim 随主题：深色下显著加深，让面板真正浮起来）*/}
      <div
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
            {image ? (
              <img
                src={resolveImageUrl(image)}
                alt={product.title}
                className="aspect-square w-full object-cover"
              />
            ) : (
              <div className="aspect-square w-full bg-[var(--surface-sunken)]" />
            )}
            {score > 0 && (
              // 角标压在恒浅色商品图上 → 恒深药丸 + 恒亮字，不跟主题翻转
              <div className="absolute left-3 top-3 flex h-12 w-12 flex-col items-center justify-center rounded-full bg-slate-900/75 shadow-lift backdrop-blur-sm">
                <span className={cn('text-base font-extrabold leading-none', scoreColorOnScrim(score))}>
                  {score.toFixed(1)}
                </span>
                <span className="text-[9px] text-white/70">评分</span>
              </div>
            )}
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

        {/* 右：评分细则 + AI 总结（依次渐入）*/}
        <div className="min-h-0 flex-1 overflow-y-auto border-t border-[var(--panel-border)] panel-sunken p-5 sm:border-l sm:border-t-0">
          <div
            className={cn(
              'transition-all duration-500',
              phase >= 1 ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
            )}
          >
            <h3 className="mb-3 text-sm font-bold text-ink">评分细则</h3>
            {comps.length > 0 ? (
              <div className="space-y-2.5">
                {comps.map(([key, v]) => (
                  <ScoreBar
                    key={key}
                    label={componentLabel(key)}
                    score={Number(v.score) || 0}
                    weight={typeof v.weight === 'number' ? v.weight : undefined}
                  />
                ))}
              </div>
            ) : (
              <p className="text-xs text-ink-muted">本次未产出细分评分</p>
            )}

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

          {/* AI 小总结 */}
          <div
            className={cn(
              'mt-5 transition-all duration-500',
              phase >= 2 ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0',
            )}
          >
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-bold text-ink">
              {/* 场景②：浏览卡片 —— 欧米按评分给表情（≥9.2 星星眼） */}
              <OmiAvatar size={20} expression={omiExpressionForScore(decision?.display_score)} />
              欧米的商品分析
            </h3>
            {summaryLoading && !summary ? (
              <div className="space-y-2">
                <div className="h-3 w-full animate-pulse rounded bg-[var(--surface-variant)]" />
                <div className="h-3 w-5/6 animate-pulse rounded bg-[var(--surface-variant)]" />
                <div className="h-3 w-3/4 animate-pulse rounded bg-[var(--surface-variant)]" />
                <p className="flex items-center gap-1.5 pt-1 text-[11px] text-ink-muted">
                  <Loader2 size={11} className="animate-spin" /> 欧米正在结合你的需求分析…
                </p>
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
