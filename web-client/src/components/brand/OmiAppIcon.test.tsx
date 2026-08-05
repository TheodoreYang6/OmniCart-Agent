import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { OmiAppIcon } from './OmiAppIcon'

describe('OmiAppIcon', () => {
  it('uses the compact transparent cat-and-cart asset', () => {
    const { container } = render(<OmiAppIcon size={44} />)
    const icon = container.querySelector('.omi-app-icon')
    const image = container.querySelector('img')

    expect(icon).toHaveStyle({ width: '44px', height: '44px' })
    expect(image).toHaveAttribute('src', '/brand/omi-cart-avatar-256-v2.webp')
    expect(icon).toHaveAttribute('aria-hidden', 'true')
  })

  it('supports semantic and active states', () => {
    const { container } = render(
      <OmiAppIcon phase="thinking" decorative={false} label="欧米正在思考" />,
    )

    const icon = container.querySelector('.omi-app-icon')
    expect(icon).toHaveAttribute('role', 'img')
    expect(icon).toHaveAttribute('aria-label', '欧米正在思考')
    expect(icon).toHaveClass('omi-app-icon-thinking')
  })
})
