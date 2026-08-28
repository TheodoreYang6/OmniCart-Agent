import { useEffect, useState } from 'react'
import { ImageOff } from 'lucide-react'
import { resolveImageUrl } from '@/config'
import { cn } from '@/lib/utils'

interface ProductImageProps {
  src?: string | null
  /** 商品 ID 可作为图片 API 的稳定兜底，避免历史/旧 SSE 漏 image_urls 时失图。 */
  productId?: string | null
  alt?: string
  className?: string
  rounded?: string
}

/** 商品图片 — 自动解析相对地址、加载中微光、失败占位。 */
export function ProductImage({ src, productId, alt = '', className, rounded = 'rounded-xl' }: ProductImageProps) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const [usingFallback, setUsingFallback] = useState(false)
  const fallback = productId ? `/api/products/${encodeURIComponent(productId)}/image` : ''
  const primaryUrl = resolveImageUrl(src)
  const fallbackUrl = resolveImageUrl(fallback)
  // SSE / historical payloads may carry an obsolete CDN or local URL.  The
  // product image endpoint is authoritative, so try it once before exposing a
  // broken-image state to the user.
  const url = usingFallback ? fallbackUrl : (primaryUrl || fallbackUrl)

  useEffect(() => {
    setLoaded(false)
    setError(false)
    setUsingFallback(false)
  }, [primaryUrl, fallbackUrl])

  const handleError = () => {
    if (!usingFallback && fallbackUrl && fallbackUrl !== url) {
      setLoaded(false)
      setUsingFallback(true)
      return
    }
    setError(true)
  }

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
        onError={handleError}
        className={cn(
          'h-full w-full object-cover transition-opacity duration-300',
          loaded ? 'opacity-100' : 'opacity-0',
        )}
      />
    </div>
  )
}
