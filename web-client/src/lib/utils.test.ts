import { describe, expect, it, vi } from 'vitest'
import { cn, debounce, formatPrice, relativeTime, shortId, trimForGrid } from './utils'

describe('utility helpers', () => {
  it('formats classes, ids and prices', () => {
    const hidden = false
    expect(cn('a', hidden ? 'b' : null, 'c')).toBe('a c')
    expect(shortId()).toHaveLength(8)
    expect(formatPrice(1299.9, 2)).toBe('¥1,299.90')
    expect(formatPrice(Number.NaN)).toBe('¥0')
  })

  it('formats all relative time bands', () => {
    vi.setSystemTime(new Date('2026-08-03T12:00:00Z'))
    expect(relativeTime()).toBe('')
    expect(relativeTime('bad')).toBe('bad')
    expect(relativeTime('2026-08-03T11:59:50Z')).toBe('刚刚')
    expect(relativeTime('2026-08-03T11:55:00Z')).toBe('5分钟前')
    expect(relativeTime('2026-08-03T10:00:00Z')).toBe('2小时前')
    expect(relativeTime('2026-08-02T12:00:00Z')).toBe('昨天')
    expect(relativeTime('2026-07-31T12:00:00Z')).toBe('3天前')
    expect(relativeTime('2026-07-01T00:00:00Z')).toBe('2026-07-01')
    vi.useRealTimers()
  })

  it('debounces and trims only orphaned grid entries', () => {
    vi.useFakeTimers()
    const fn = vi.fn()
    const debounced = debounce(fn, 20)
    debounced()
    debounced()
    vi.advanceTimersByTime(20)
    expect(fn).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
    expect(trimForGrid([1, 2, 3, 4])).toEqual([1, 2, 3])
    expect(trimForGrid([1, 2, 3])).toEqual([1, 2, 3])
    expect(trimForGrid([1, 2, 3, 4, 5])).toHaveLength(5)
  })
})
