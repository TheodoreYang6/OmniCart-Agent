import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ChevronDown, ShoppingCart, ShieldAlert } from 'lucide-react'
import { api } from '@/api/client'
import type { Sku } from '@/api/types'
import { ProductImage } from '@/components/ui/ProductImage'
import { Omi } from '@/components/brand/Omi'
import { StarRating } from '@/components/product/ProductCard'
import { LoadingBlock } from '@/components/ui/Spinner'
import { EmptyState } from '@/components/ui/EmptyState'
import { useCartStore } from '@/store/cartStore'
import { useChatStore } from '@/store/chatStore'
import { toast } from '@/store/toastStore'
import { formatPrice } from '@/lib/utils'
import { cn } from '@/lib/utils'

export function ProductDetailPage() {
  const { productId = '' } = useParams()
  const navigate = useNavigate()
  const addToCart = useCartStore((s) => s.addToCart)
  const askAgent = useChatStore((s) => s.askAgent)

  const [activeImage, setActiveImage] = useState(0)
  const [selectedSku, setSelectedSku] = useState<Sku | null>(null)
  const [openFaq, setOpenFaq] = useState<number | null>(null)

  const productQuery = useQuery({
    queryKey: ['product', productId],
    queryFn: ({ signal }) => api.getProduct(productId, signal),
    enabled: Boolean(productId),
  })
  const product = productQuery.data
  useEffect(() => {
    setSelectedSku(product?.skus?.[0] ?? null)
    setActiveImage(0)
    setOpenFaq(null)
  }, [product])

  if (productQuery.isPending) return <LoadingBlock text="加载商品详情…" />
  if (productQuery.isError || !product) {
    return (
      <EmptyState
        title="商品详情加载失败"
        description={productQuery.error instanceof Error ? productQuery.error.message : '它可能已下架或网络暂时不可用'}
        action={
          <div className="mt-2 flex gap-2"><button onClick={() => void productQuery.refetch()} className="btn-primary">重试</button><button onClick={() => navigate('/shop')} className="btn-outline">返回商品页</button></div>
        }
      />
    )
  }

  const price = selectedSku && selectedSku.price > 0 ? selectedSku.price : product.price
  const summary = product.review_summary
  const images = product.image_urls?.length ? product.image_urls : ['']

  const handleAsk = () => {
    askAgent(product.product_id, product.title)
    navigate('/chat')
  }

  return (
    <div className="aurora-bg flex h-full flex-col">
      {/* 顶栏：玻璃条 */}
      <header className="glass-strong z-10 flex items-center gap-2 border-b border-[var(--line)] px-3 py-3">
        <button
          onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/shop')}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-soft transition hover:bg-[var(--glass-bg-strong)]"
          aria-label="返回"
        >
          <ArrowLeft size={20} />
        </button>
        <span className="truncate font-medium text-ink">商品详情</span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto pb-24">
        <div className="mx-auto max-w-4xl px-4 py-4 lg:grid lg:grid-cols-2 lg:gap-6">
          {/* 图片 */}
          <div>
            <div className="overflow-hidden rounded-2xl shadow-lift">
              <ProductImage
                src={images[activeImage]}
                alt={product.title}
                rounded="rounded-none"
                className="aspect-square w-full"
              />
            </div>
            {images.length > 1 && (
              <div className="no-scrollbar mt-3 flex gap-2 overflow-x-auto">
                {images.map((img, i) => (
                  <button
                    key={i}
                    onClick={() => setActiveImage(i)}
                    className={cn(
                      'h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 transition-all duration-200',
                      i === activeImage ? 'border-brand-500 shadow-glow' : 'border-transparent opacity-70 hover:opacity-100',
                    )}
                  >
                    <ProductImage src={img} rounded="rounded-md" className="h-full w-full" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 信息 */}
          <div className="mt-4 lg:mt-0">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-price">{formatPrice(price)}</span>
            </div>
            <h1 className="mt-2 text-lg font-semibold leading-snug text-ink">{product.title}</h1>
            <div className="mt-1.5 flex items-center gap-2 text-sm text-ink-muted">
              <span className="gradient-brand rounded-md px-2 py-0.5 text-white">
                {product.brand}
              </span>
              <span>{product.category}</span>
              {product.sub_category && <span>· {product.sub_category}</span>}
            </div>

            {summary && summary.total_count > 0 && (
              <div className="glass mt-3 flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
                <span className="flex items-center gap-1">
                  <StarRating rating={summary.avg_rating} size={15} />
                  <span className="font-semibold text-ink">{summary.avg_rating.toFixed(1)}</span>
                </span>
                <span className="text-ink-muted">{summary.total_count} 条评价</span>
                <span className="text-emerald-600 dark:text-emerald-400">好评 {summary.positive_count}</span>
                {summary.negative_count > 0 && (
                  <span className="text-rose-500 dark:text-rose-400">差评 {summary.negative_count}</span>
                )}
              </div>
            )}

            {summary?.risk_tags && summary.risk_tags.length > 0 && (
              <div className="risk-strip mt-2 flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm">
                <ShieldAlert size={16} />
                {summary.risk_tags.join('、')}
              </div>
            )}

            {/* SKU */}
            {product.skus && product.skus.length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-sm font-medium text-ink">选择规格</p>
                <div className="flex flex-wrap gap-2">
                  {product.skus.map((sku) => {
                    const label =
                      Object.entries(sku.properties ?? {})
                        .map(([k, v]) => `${k}:${v}`)
                        .join(' · ') || '默认'
                    const active = selectedSku?.sku_id === sku.sku_id
                    return (
                      <button
                        key={sku.sku_id}
                        onClick={() => setSelectedSku(sku)}
                        className={cn(
                          'rounded-full border px-3.5 py-2 text-sm transition-all duration-200',
                          active
                            ? 'gradient-brand border-transparent text-white shadow-glow'
                            : 'border-[var(--field-border)] bg-[var(--glass-bg)] text-ink-soft backdrop-blur hover:border-brand-300 hover:text-brand-600',
                        )}
                      >
                        {label}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 桌面端操作按钮 */}
            <div className="mt-5 hidden gap-2 lg:flex">
              <button onClick={handleAsk} className="btn-outline flex-1">
                <Omi size={20} /> 问欧米
              </button>
              <button
                onClick={async () => {
                  const ok = await addToCart(product.product_id, selectedSku?.sku_id)
                  if (ok) toast.success('已加入购物车')
                }}
                className="btn-primary flex-1"
              >
                <ShoppingCart size={18} /> 加入购物车
              </button>
            </div>
          </div>

          {/* 描述 / FAQ / 评价 —— 跨两列 */}
          <div className="lg:col-span-2">
            {product.marketing_description && (
              <Section title="商品介绍">
                <p className="whitespace-pre-line text-sm leading-relaxed text-ink-soft">
                  {product.marketing_description}
                </p>
              </Section>
            )}

            {product.official_faq && product.official_faq.length > 0 && (
              <Section title="常见问题">
                <div className="divide-y divide-slate-100">
                  {product.official_faq.map((f, i) => (
                    <div key={i}>
                      <button
                        onClick={() => setOpenFaq(openFaq === i ? null : i)}
                        className="flex w-full items-center justify-between gap-2 py-3 text-left"
                        aria-expanded={openFaq === i}
                        aria-controls={`faq-answer-${i}`}
                      >
                        <span className="text-sm font-medium text-ink">{f.question}</span>
                        <ChevronDown
                          size={18}
                          className={cn(
                            'shrink-0 text-ink-muted transition',
                            openFaq === i && 'rotate-180',
                          )}
                        />
                      </button>
                      {openFaq === i && (
                        <p id={`faq-answer-${i}`} className="pb-3 text-sm leading-relaxed text-ink-muted">{f.answer}</p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {product.user_reviews && product.user_reviews.length > 0 && (
              <Section title={`用户评价 (${product.user_reviews.length})`}>
                <div className="space-y-3">
                  {product.user_reviews.map((r, i) => (
                    <div key={i} className="rounded-xl bg-[var(--field-bg)] p-3 backdrop-blur">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-ink">{r.nickname}</span>
                        <StarRating rating={r.rating} />
                      </div>
                      <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{r.content}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        </div>
      </div>

      {/* 移动端底部操作栏：粘性玻璃 */}
      <div className="glass-strong flex items-center gap-2 border-t border-[var(--line)] px-4 py-3 lg:hidden">
        <button onClick={handleAsk} className="btn-outline flex-1">
          <Omi size={20} /> 问欧米
        </button>
        <button
          onClick={async () => {
            const ok = await addToCart(product.product_id, selectedSku?.sku_id)
            if (ok) toast.success('已加入购物车')
          }}
          className="btn-primary flex-[1.4]"
        >
          <ShoppingCart size={18} /> 加入购物车
        </button>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass mt-5 p-4">
      <h2 className="mb-2 flex items-center gap-2 text-base font-semibold text-ink">
        <span className="gradient-brand h-4 w-1 rounded-full" />
        {title}
      </h2>
      {children}
    </div>
  )
}
