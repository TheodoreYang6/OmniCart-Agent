import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OmiPerch } from './OmiPerch'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('OmiPerch', () => {
  it('uses the corrected two-paw v4 responsive asset and matching eye coordinates', () => {
    const { container } = render(<OmiPerch />)
    const image = container.querySelector('img')
    expect(image).toHaveAttribute('src', '/brand/omi-perch-v4.png')
    expect(image).toHaveAttribute('width', '640')
    expect(image).toHaveAttribute('height', '559')
    expect(container.querySelector('source[type="image/avif"]')).toHaveAttribute(
      'srcset',
      expect.stringContaining('omi-perch-v4-640.avif'),
    )
    expect(container.querySelector('svg[viewBox="0 0 640 559"]')).toBeInTheDocument()
    expect(container.querySelectorAll('[data-omi-pupil]')).toHaveLength(2)
  })

  it('supports non-interactive decorative use without scheduling reactions', () => {
    vi.useFakeTimers()
    const { container } = render(<OmiPerch interactive={false} />)
    const root = container.querySelector('[data-omi-perch]')
    expect(root).not.toHaveAttribute('role')
    expect(root).toHaveAttribute('aria-hidden', 'true')
    fireEvent.click(root!)
    expect(container.querySelector('[data-omi-heart]')).not.toBeInTheDocument()
  })

  it('keeps keyboard interaction available for the semantic hero', () => {
    vi.useFakeTimers()
    const { container } = render(<OmiPerch />)
    fireEvent.keyDown(container.querySelector('[data-omi-perch]')!, { key: 'Enter' })
    expect(container.querySelectorAll('[data-omi-heart]')).toHaveLength(3)
    act(() => vi.advanceTimersByTime(1500))
    expect(container.querySelector('[data-omi-heart]')).not.toBeInTheDocument()
  })

  it('tracks a fine pointer through RAF and cleans up on unmount', () => {
    vi.useFakeTimers()
    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      matches: query.includes('pointer: fine'),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    const { container, unmount } = render(<OmiPerch />)
    fireEvent.mouseMove(window, { clientX: 500, clientY: 300 })
    act(() => vi.advanceTimersByTime(20))
    expect(container.querySelector('[data-omi-pupil="0"]')).not.toHaveAttribute('transform', 'translate(0 0)')
    unmount()
    fireEvent.mouseMove(window, { clientX: 100, clientY: 100 })
  })

  it('blinks on schedule and keeps reduced-motion interaction static', () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    const { container, unmount } = render(<OmiPerch />)
    act(() => vi.advanceTimersByTime(2801))
    expect(container.querySelectorAll('svg ellipse')).toHaveLength(4)
    act(() => vi.advanceTimersByTime(140))
    expect(container.querySelectorAll('svg ellipse')).toHaveLength(2)
    unmount()

    vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    const reduced = render(<OmiPerch />)
    fireEvent.click(reduced.container.querySelector('[data-omi-perch]')!)
    expect(reduced.container.querySelector('[data-omi-heart]')).not.toBeInTheDocument()
  })
})
