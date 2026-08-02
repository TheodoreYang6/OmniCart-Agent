import { useState } from 'react'
import {
  Activity,
  FileSearch,
  ListChecks,
  Route,
  ShieldCheck,
} from 'lucide-react'
import type {
  DecisionResult,
  EvidenceItem,
  Product,
  TraceStepItem,
} from '@/api/types'
import { componentLabel, levelStyle, scoreColor } from '@/lib/format'
import { cn } from '@/lib/utils'

export interface InsightData {
  products: Product[]
  decisionResults: DecisionResult[]
  evidenceList: EvidenceItem[]
  traceSteps: TraceStepItem[]
  retrievalPlan?: Record<string, unknown> | null
  sufficiencyReport?: Record<string, unknown> | null
  constraints?: Record<string, unknown> | null
  harnessReport?: Record<string, unknown> | null
}

type TabKey = 'trace' | 'score' | 'evidence' | 'plan'

const TABS: { key: TabKey; label: string; icon: typeof Route }[] = [
  { key: 'trace', label: '推理轨迹', icon: Route },
  { key: 'score', label: '决策评分', icon: ListChecks },
  { key: 'evidence', label: '证据链', icon: FileSearch },
  { key: 'plan', label: '检索计划', icon: Activity },
]

export function AgentInsights({ data }: { data: InsightData }) {
  const [tab, setTab] = useState<TabKey>('trace')
  const titleOf = (pid: string) =>
    data.products.find((p) => p.product_id === pid)?.title ?? pid

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-[var(--line)] px-3">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              'flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition',
              tab === t.key
                ? 'border-brand-500 text-brand-600'
                : 'border-transparent text-ink-muted hover:text-ink',
            )}
          >
            <t.icon size={15} />
            {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === 'trace' && <TraceView steps={data.traceSteps} />}
        {tab === 'score' && <ScoreView results={data.decisionResults} titleOf={titleOf} />}
        {tab === 'evidence' && <EvidenceView list={data.evidenceList} />}
        {tab === 'plan' && (
          <PlanView
            plan={data.retrievalPlan}
            sufficiency={data.sufficiencyReport}
            constraints={data.constraints}
            harness={data.harnessReport}
          />
        )}
      </div>
    </div>
  )
}

function TraceView({ steps }: { steps: TraceStepItem[] }) {
  if (!steps.length) return <Empty text="暂无推理轨迹" />
  return (
    <ol className="relative space-y-4 pl-6">
      <span className="absolute left-[9px] top-1 h-[calc(100%-1rem)] w-px bg-[var(--field-border)]" />
      {steps.map((s) => {
        const ok = s.status === 'success'
        const skip = s.status === 'skipped'
        return (
          <li key={s.step_id} className="relative">
            <span
              className={cn(
                'absolute -left-6 top-0.5 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 border-[var(--surface)] text-white shadow',
                ok ? 'bg-emerald-500' : skip ? 'bg-[var(--field-border)]' : 'bg-amber-500',
              )}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-white" />
            </span>
            <div className="rounded-xl border border-[var(--line)] bg-[var(--card-bg)] p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-ink">{s.agent_name}</span>
                <span className="text-xs text-ink-muted">{s.latency_ms}ms</span>
              </div>
              <p className="mt-0.5 text-xs text-brand-600">{s.action}</p>
              {s.output_summary && (
                <p className="mt-1 text-xs leading-snug text-ink-muted">{s.output_summary}</p>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function ScoreView({
  results,
  titleOf,
}: {
  results: DecisionResult[]
  titleOf: (pid: string) => string
}) {
  if (!results.length) return <Empty text="暂无评分数据" />
  return (
    <div className="space-y-4">
      {results.slice(0, 8).map((r) => {
        const ls = levelStyle(r.recommendation_level)
        const comps = Object.entries(r.component_scores ?? {}).filter(
          ([, v]) => typeof v?.score === 'number',
        )
        return (
          <div key={r.product_id} className="rounded-xl border border-[var(--line)] bg-[var(--card-bg)] p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="line-clamp-1 text-sm font-medium text-ink">{titleOf(r.product_id)}</p>
              <span className={cn('shrink-0 text-lg font-bold', scoreColor(r.display_score))}>
                {r.display_score.toFixed(1)}
              </span>
            </div>
            <span
              className={cn(
                'mt-1 inline-block rounded-md border px-1.5 py-0.5 text-[11px] font-medium',
                ls.bg,
                ls.text,
                ls.border,
              )}
            >
              {ls.label}
            </span>
            {comps.length > 0 && (
              <div className="mt-2.5 space-y-1.5">
                {comps.slice(0, 7).map(([key, v]) => {
                  const pct = Math.max(0, Math.min(100, (Number(v.score) || 0) * 100))
                  return (
                    <div key={key} className="flex items-center gap-2">
                      <span className="w-16 shrink-0 text-[11px] text-ink-muted">
                        {componentLabel(key)}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--surface-variant)]">
                        <div
                          className="h-full rounded-full bg-brand-400"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-8 shrink-0 text-right text-[11px] font-medium text-ink-muted">
                        {(Number(v.score) * 10).toFixed(1)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
            {r.risk_factors.length > 0 && (
              <p className="risk-strip mt-2 rounded-md px-2 py-1 text-[11px]">
                ⚠ {r.risk_factors.join('，')}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

function EvidenceView({ list }: { list: EvidenceItem[] }) {
  if (!list.length) return <Empty text="暂无证据引用" />
  const typeCn: Record<string, string> = {
    policy: '政策',
    review: '评价',
    marketing: '营销',
    visual: '视觉',
    text: '文本',
  }
  return (
    <div className="space-y-2">
      {list.slice(0, 20).map((e, i) => (
        <div
          key={`${e.evidence_id}-${i}`}
          className="rounded-xl border border-[var(--line)] bg-[var(--card-bg)] p-3"
        >
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
              {typeCn[e.source_type] ?? e.source_type}
            </span>
            <span className="font-mono text-[11px] text-ink-muted">{e.evidence_id}</span>
            <span className="ml-auto text-[11px] text-ink-muted">
              可信度 {(e.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="mt-1.5 text-xs leading-snug text-ink-soft">{e.content}</p>
        </div>
      ))}
    </div>
  )
}

function PlanView({
  plan,
  sufficiency,
  constraints,
  harness,
}: {
  plan?: Record<string, unknown> | null
  sufficiency?: Record<string, unknown> | null
  constraints?: Record<string, unknown> | null
  harness?: Record<string, unknown> | null
}) {
  const rows = (obj?: Record<string, unknown> | null) =>
    Object.entries(obj ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== '')

  const Section = ({
    title,
    icon: Icon,
    obj,
  }: {
    title: string
    icon: typeof Activity
    obj?: Record<string, unknown> | null
  }) => {
    const r = rows(obj)
    if (!r.length) return null
    return (
      <div className="rounded-xl border border-[var(--line)] bg-[var(--card-bg)] p-3">
        <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ink">
          <Icon size={15} className="text-brand-500" />
          {title}
        </p>
        <dl className="space-y-1">
          {r.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 text-xs">
              <dt className="shrink-0 text-ink-muted">{k}</dt>
              <dd className="text-right text-ink-soft">
                {Array.isArray(v) ? v.join(', ') : String(v)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    )
  }

  const hasAny =
    rows(plan).length || rows(sufficiency).length || rows(constraints).length || rows(harness).length
  if (!hasAny) return <Empty text="暂无检索计划信息" />

  return (
    <div className="space-y-3">
      <Section title="检索计划" icon={Activity} obj={plan} />
      <Section title="约束条件" icon={ListChecks} obj={constraints} />
      <Section title="充分性报告" icon={ShieldCheck} obj={sufficiency} />
      <Section title="校验报告" icon={ShieldCheck} obj={harness} />
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <p className="py-10 text-center text-sm text-ink-muted">{text}</p>
}
