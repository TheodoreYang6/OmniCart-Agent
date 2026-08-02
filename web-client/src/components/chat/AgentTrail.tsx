import { useMemo, useState } from 'react'
import {
  Brain,
  Search,
  ArrowDownWideNarrow,
  Gauge,
  PenLine,
  Wrench,
  Sparkles,
  Check,
  ChevronDown,
  Loader2,
} from 'lucide-react'
import type { TraceStepItem } from '@/api/types'
import { AGENT_NAME } from '@/config'
import { cn } from '@/lib/utils'

/**
 * Agent 推理可视化（P2）——把"检索→重排→评分→生成"的思考轨迹做成一等公民 UI。
 *
 * 两种形态：
 *  - <AgentTrail steps />      流式进行中：迷你卡片流，完成步打勾、当前步 spinner+光环
 *  - <TrailSummary steps />    回答完成后：折叠为一行「欧米思考了 N 步 · 用时 X 秒」，点击展开回看
 *
 * 数据源全部复用现有管道（SSE status 累积 / result 帧 trace_steps），零后端改动。
 */

/** 状态文案 → 步骤图标（关键词映射，未命中给通用星标） */
function iconFor(text: string) {
  if (/理解|分析|意图|拆解/.test(text)) return Brain
  if (/检索|搜索|召回|找|挑选/.test(text)) return Search
  if (/重排|排序|精排/.test(text)) return ArrowDownWideNarrow
  if (/评分|决策|评估|甄选/.test(text)) return Gauge
  if (/生成|回答|组织|撰写/.test(text)) return PenLine
  if (/工具|执行|下单|购物车/.test(text)) return Wrench
  return Sparkles
}

/** 流式进行中的卡片流：最后一项为当前步（spinner+光环），其余为已完成（打勾） */
export function AgentTrail({ steps }: { steps: string[] }) {
  if (steps.length === 0) return null
  return (
    <div className="flex flex-col gap-1.5">
      {steps.map((s, i) => {
        const Icon = iconFor(s)
        const isCurrent = i === steps.length - 1
        return (
          <div
            key={`${i}-${s}`}
            className={cn(
              'flex w-fit max-w-full items-center gap-2 rounded-xl px-3 py-1.5 text-xs backdrop-blur transition-all',
              isCurrent
                ? 'animate-pulse-glow border border-brand-200 bg-[var(--glass-bg-strong)] text-brand-700'
                : 'border border-[var(--card-border)] bg-[var(--card-bg)] text-ink-muted',
            )}
          >
            <span
              className={cn(
                'flex h-5 w-5 shrink-0 items-center justify-center rounded-lg',
                isCurrent ? 'gradient-brand text-white' : 'bg-[var(--surface-variant)] text-brand-400',
              )}
            >
              <Icon size={12} />
            </span>
            <span className="line-clamp-1">{s}</span>
            {isCurrent ? (
              <Loader2 size={12} className="shrink-0 animate-spin text-brand-500" />
            ) : (
              <Check size={12} className="shrink-0 text-emerald-500" />
            )}
          </div>
        )
      })}
    </div>
  )
}

/** 完成后的折叠摘要：一行概览，点击展开逐步回看（agent 名 + 动作 + 耗时） */
export function TrailSummary({ steps }: { steps: TraceStepItem[] }) {
  const [open, setOpen] = useState(false)
  const totalMs = useMemo(
    () => steps.reduce((acc, s) => acc + (s.latency_ms || 0), 0),
    [steps],
  )
  if (steps.length === 0) return null

  return (
    <div className="w-fit max-w-full">
      <button
        onClick={() => setOpen(!open)}
        className="status-pill font-medium transition hover:shadow-glow"
      >
        <Sparkles size={13} className="text-brand-500" />
        {AGENT_NAME}思考了 {steps.length} 步 · 用时 {(totalMs / 1000).toFixed(1)}s
        <ChevronDown
          size={13}
          className={cn('transition-transform duration-200', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="mt-1.5 flex flex-col gap-1 animate-fade-in">
          {steps.map((s, i) => {
            const Icon = iconFor(`${s.agent_name}${s.action}`)
            return (
              <div
                key={s.step_id || i}
                className="flex items-center gap-2 rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)] px-3 py-1.5 text-xs text-ink-soft backdrop-blur"
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-variant)] text-brand-400">
                  <Icon size={12} />
                </span>
                <span className="font-medium text-ink">{s.agent_name}</span>
                <span className="line-clamp-1 text-ink-muted">{s.action}</span>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-muted">
                  {s.latency_ms}ms
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
