/**
 * 决策等级 / 评分 展示辅助 — 对齐后端 recommendation_level 与安卓端 _LEVEL_CN。
 */

export const LEVEL_CN: Record<string, string> = {
  strong_recommend: '高度匹配',
  recommended: '适合考虑',
  worth_considering: '有条件匹配',
  cautious: '需留意',
  insufficient_evidence: '信息有限',
  not_recommended: '暂不建议',
}

export interface LevelStyle {
  label: string
  text: string
  bg: string
  border: string
  dot: string
}

export function levelStyle(level: string): LevelStyle {
  const label = LEVEL_CN[level] ?? level ?? ''
  // 深色下一律改“半透底 + 提亮字 + 半透边”：浅底（*-50）在近黑面板上发脏，
  // 700 挡字色也会发闷，导致徒标整体“发淡”
  switch (level) {
    case 'strong_recommend':
      return {
        label,
        text: 'text-emerald-700 dark:text-emerald-300',
        bg: 'bg-emerald-50 dark:bg-emerald-500/15',
        border: 'border-emerald-200 dark:border-emerald-400/30',
        dot: 'bg-emerald-500 dark:bg-emerald-400',
      }
    case 'recommended':
      return {
        label,
        text: 'text-brand-700 dark:text-brand-200',
        bg: 'bg-brand-50 dark:bg-brand-500/18',
        border: 'border-brand-200 dark:border-brand-400/35',
        dot: 'bg-brand-500 dark:bg-brand-300',
      }
    case 'worth_considering':
      return {
        label,
        text: 'text-sky-700 dark:text-sky-300',
        bg: 'bg-sky-50 dark:bg-sky-500/15',
        border: 'border-sky-200 dark:border-sky-400/30',
        dot: 'bg-sky-500 dark:bg-sky-400',
      }
    case 'cautious':
      return {
        label,
        text: 'text-amber-700 dark:text-amber-300',
        bg: 'bg-amber-50 dark:bg-amber-500/15',
        border: 'border-amber-200 dark:border-amber-400/30',
        dot: 'bg-amber-500 dark:bg-amber-400',
      }
    case 'not_recommended':
      return {
        label,
        text: 'text-rose-700 dark:text-rose-300',
        bg: 'bg-rose-50 dark:bg-rose-500/15',
        border: 'border-rose-200 dark:border-rose-400/30',
        dot: 'bg-rose-500 dark:bg-rose-400',
      }
    default:
      return {
        label,
        text: 'text-slate-600 dark:text-slate-300',
        bg: 'bg-slate-50 dark:bg-white/8',
        border: 'border-slate-200 dark:border-white/15',
        dot: 'bg-slate-400 dark:bg-slate-300',
      }
  }
}

/** 数据集品类 → emoji 图标。 */
export const CATEGORY_ICON: Record<string, string> = {
  数码电子: '💻',
  美妆护肤: '💄',
  服饰运动: '👟',
  食品生活: '🍜',
  食品饮料: '🍜',
  家居用品: '🏠',
  母婴用品: '🍼',
  运动户外: '⛰️',
  个护清洁: '🧴',
}

export function categoryIcon(cat?: string): string {
  if (!cat) return '🛍️'
  return CATEGORY_ICON[cat] ?? '🛍️'
}
