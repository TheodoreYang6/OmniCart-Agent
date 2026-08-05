import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ComparisonTableData } from '@/api/types'

interface ComparisonTableProps {
  table: ComparisonTableData
  analysis?: Record<string, unknown> | null
}

/**
 * 聚焦分析对比表 — 对应后端 comparison_table：
 * { dimensions: string[], target_values: string[], alternative_values: string[][] }
 */
export function ComparisonTable({ table, analysis }: ComparisonTableProps) {
  const dimensions = table.dimensions ?? []
  const targetValues = table.target_values ?? []
  const altValues = table.alternative_values ?? []
  if (!dimensions.length) return null

  const targetTitle = String(analysis?.title ?? '目标商品')

  return (
    <div className="glass overflow-hidden">
      <div className="flex items-center gap-1.5 bg-brand-50 px-4 py-2.5 text-sm font-semibold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
        <Sparkles size={15} />
        同类对比
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--line)] text-xs text-ink-muted">
              <th className="px-3 py-2 text-left font-medium">维度</th>
              <th className="px-3 py-2 text-left font-medium text-brand-600">
                {targetTitle.slice(0, 12)}
              </th>
              {altValues.map((_, i) => (
                <th key={i} className="px-3 py-2 text-left font-medium">
                  备选{i + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dimensions.map((dim, r) => (
              <tr key={dim} className={cn(r % 2 === 1 && 'bg-[var(--surface-sunken)]/60')}>
                <td className="px-3 py-2 text-ink-muted">{dim}</td>
                <td className="px-3 py-2 font-medium text-brand-700">{targetValues[r] ?? '-'}</td>
                {altValues.map((col, i) => (
                  <td key={i} className="px-3 py-2 text-ink-soft">
                    {col[r] ?? '-'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
