import { act, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Omi, OMI_VISUAL_STATES } from './Omi'

describe('Omi', () => {
  it('isolates SVG definition ids across instances', () => {
    const { container } = render(<><Omi expression="star" /><Omi expression="star" /></>)
    const ids = Array.from(container.querySelectorAll('defs [id]')).map((node) => node.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('supports decorative and semantic modes', () => {
    const { rerender, container } = render(<Omi />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    rerender(<Omi decorative={false} label="欧米正在搜索" />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-label', '欧米正在搜索')
  })

  it('keeps the shared product state mapping stable', () => {
    expect(OMI_VISUAL_STATES.searching).toEqual({ expression: 'search', phase: 'thinking' })
    expect(OMI_VISUAL_STATES.added.expression).toBe('wink')
    expect(OMI_VISUAL_STATES.error.expression).toBe('surprised')
  })

  it('renders every expression plus body and phase variants', () => {
    vi.useFakeTimers()
    const expressions = ['happy', 'star', 'thinking', 'wink', 'sleepy', 'search', 'surprised', 'pleading', 'smug'] as const
    const { container, rerender } = render(<Omi expression="happy" withBody phase="thinking" float />)
    for (const expression of expressions) rerender(<Omi expression={expression} withBody phase="talking" />)
    act(() => vi.advanceTimersByTime(7000))
    expect(container.querySelector('text')?.textContent).toContain('omi')
    vi.useRealTimers()
  })
})
