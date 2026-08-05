import { fireEvent, render, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProductImage } from './ProductImage'

describe('ProductImage', () => {
  it('resets loaded state when src changes', async () => {
    const view = render(<ProductImage src="/one.jpg" alt="商品" />)
    const first = view.getByAltText('商品')
    fireEvent.load(first)
    expect(first).toHaveClass('opacity-100')
    view.rerender(<ProductImage src="/two.jpg" alt="商品" />)
    await waitFor(() => expect(view.getByAltText('商品')).toHaveClass('opacity-0'))
  })

  it('shows a fallback after image failure and handles an empty source', () => {
    const view = render(<ProductImage src="/broken.jpg" alt="坏图" />)
    fireEvent.error(view.getByAltText('坏图'))
    expect(view.queryByAltText('坏图')).not.toBeInTheDocument()
    expect(view.getByRole('img', { name: '坏图图片不可用' })).toBeVisible()
    view.rerender(<ProductImage src="" alt="空图" />)
    expect(view.getByRole('img', { name: '空图图片不可用' })).toBeVisible()
  })
})
