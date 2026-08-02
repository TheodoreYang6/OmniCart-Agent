import { useState } from 'react'
import { ChevronDown, FileText, MessageSquareQuote, Star, BookOpen } from 'lucide-react'
import type { EvidenceItem } from '@/api/types'
import { cn } from '@/lib/utils'

/**
 * 证据外显折叠条（P3）——回答依据的证据做成一等公民 UI。
 * 折叠态一行「依据 N 条证据」；展开列出：来源图标 + 内容摘要 + 置信度徽标。
 * 数据复用消息里现有 evidenceList（SSE result 帧），零后端改动。
 */

const SOURCE_ICON: Record<string, typeof FileText> = {
  review: MessageSquareQuote, // 用户评价
  faq: BookOpen, // 官方 FAQ
  description: FileText, // 商品描述
  rating: Star, // 评分
}

const SOURCE_LABEL: Record<string, string> = {
  review: '用户评价',
  faq: '官方FAQ',
  description: '商品描述',
  rating: '评分数据',
}

function confidenceTone(c: number) {
  if (c >= 0.75) return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
  if (c >= 0.5) return 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'
  return 'bg-[var(--surface-variant)] text-ink-muted dark:bg-[var(--surface-sunken)]0/15 dark:text-ink-muted'
}

export function EvidenceStrip({ items }: { items: EvidenceItem[] }) {
  const [open, setOpen] = useState(false)
  if (items.length === 0) return null

  return (
    <div className="w-fit max-w-full">
      <button
        onClick={() => setOpen(!open)}
        className="status-pill font-medium transition hover:shadow-glow"
      >
        <FileText size={13} className="text-brand-500" />
        依据 {items.length} 条证据
        <ChevronDown
          size={13}
          className={cn('transition-transform duration-200', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="mt-1.5 flex max-w-xl flex-col gap-1 animate-fade-in">
          {items.slice(0, 8).map((e, i) => {
            const Icon = SOURCE_ICON[e.source_type] ?? FileText
            return (
              <div
                key={e.evidence_id || i}
                className="flex items-start gap-2 rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] px-3 py-2 text-xs backdrop-blur"
              >
                <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-variant)] text-brand-400">
                  <Icon size={12} />
                </span>
                <div className="min-w-0 flex-1">
                  <span className="mr-1.5 font-medium text-ink">
                    {SOURCE_LABEL[e.source_type] ?? e.source_type}
                  </span>
                  <span className="text-ink-muted">{e.content}</span>
                </div>
                {typeof e.confidence === 'number' && (
                  <span
                    className={cn(
                      'shrink-0 rounded-full px-1.5 py-px font-mono text-[10px]',
                      confidenceTone(e.confidence),
                    )}
                  >
                    {Math.round(e.confidence * 100)}%
                  </span>
                )}
              </div>
            )
          })}
          {items.length > 8 && (
            <p className="px-1 text-[11px] text-ink-muted">
              还有 {items.length - 8} 条，完整证据见「推理过程」面板
            </p>
          )}
        </div>
      )}
    </div>
  )
}
