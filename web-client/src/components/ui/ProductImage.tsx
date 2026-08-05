import { useEffect, useState } from 'react'
import { ImageOff } from 'lucide-react'
import { resolveImageUrl } from '@/config'
import { cn } from '@/lib/utils'

interface ProductImageProps {
  src?: string | null
  alt?: string
  className?: string
  rounded?: string
}

/** 商品图片 — 自动解析相对地址、加载中微光、失败占位。 */
export function ProductImage({ src, alt = '', className, rounded = 'rounded-xl' }: ProductImageProps) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const url = resolveImageUrl(src)

  useEffect(() => {
    setLoaded(false)
    setError(false)
  }, [url])

  if (!url || error) {
    return (
      <div
        role="img"
        aria-label={alt ? `${alt}图片不可用` : '图片不可用'}
        className={cn(
          'flex items-center justify-center bg-[var(--product-tile)] text-ink-muted',
          rounded,
          className,
        )}
      >
        <ImageOff size={28} aria-hidden="true" />
      </div>
    )
  }

  return (
    <div className={cn('relative overflow-hidden bg-[var(--product-tile)]', rounded, className)}>
      {!loaded && <div className="absolute inset-0 shimmer bg-[var(--product-tile)]" />}
      <img
        src={url}
        alt={alt}
        loading="lazy"
        decoding="async"
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        className={cn(
          'h-full w-full object-cover transition-opacity duration-300',
          loaded ? 'opacity-100' : 'opacity-0',
        )}
      />
    </div>
  )
}
