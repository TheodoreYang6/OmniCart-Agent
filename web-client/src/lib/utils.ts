import { clsx, type ClassValue } from 'clsx'

/** Tailwind 类名合并。 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs)
}

/** 生成 8 位短 sessionId（对齐安卓端 UUID.take(8)）。 */
export function shortId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().slice(0, 8)
  }
  return Math.random().toString(36).slice(2, 10)
}

/** 价格格式化：¥1,299 / ¥1,299.90 */
export function formatPrice(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) return '¥0'
  const fixed = value.toFixed(decimals)
  const [int, dec] = fixed.split('.')
  const withComma = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `¥${withComma}${dec ? '.' + dec : ''}`
}

/** 相对时间：刚刚 / 5分钟前 / 昨天 / 3天前 / yyyy-MM-dd */
export function relativeTime(iso?: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = Date.now() - t
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min}分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour}小时前`
  const day = Math.floor(hour / 24)
  if (day === 1) return '昨天'
  if (day < 7) return `${day}天前`
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`
}

/** 简单防抖。 */
export function debounce<T extends (...args: never[]) => void>(fn: T, delay = 300): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: never[]) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delay)
  }) as T
}

/**
 * 网格展示去尾单：每行 `cols` 个时，若末行只落单 1 个（length % cols === 1）则砂掉最后一个。
 *
 * 仅末行落单才丑：4→3、7→6、10→9（cols=3）；而 5(3/2)、8(3/3/2) 末行 2 个可接受，不动。
 * 列表长度 ≤ cols（包括只有 1 个）时不处理（砂了会变空或不必要）。
 * 约定调用方传入已按优先级（得分）降序的列表，故砂掉的是最低优先级项。
 */
export function trimForGrid<T>(items: T[], cols = 3): T[] {
  if (items.length > cols && items.length % cols === 1) {
    return items.slice(0, -1)
  }
  return items
}
