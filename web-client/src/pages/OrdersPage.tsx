import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Clock3, PackageCheck, ReceiptText, ShoppingBag } from 'lucide-react'
import { api } from '@/api/client'
import type { Order } from '@/api/types'
import { ProductImage } from '@/components/ui/ProductImage'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingBlock } from '@/components/ui/Spinner'
import { useAuthStore } from '@/store/authStore'
import { formatPrice, relativeTime } from '@/lib/utils'

const STATUS_CN: Record<string, string> = {
  pending: '待支付',
  paid: '已支付',
  shipped: '运输中',
  completed: '已完成',
  cancelled: '已取消',
}

const STATUS_STYLE: Record<string, string> = {
  pending: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  paid: 'bg-sky-500/10 text-sky-700 dark:text-sky-300',
  shipped: 'bg-brand-500/10 text-brand-700 dark:text-brand-300',
  completed: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  cancelled: 'bg-rose-500/10 text-rose-700 dark:text-rose-300',
}

export function OrdersPage() {
  const navigate = useNavigate()
  const effectiveUserId = useAuthStore((s) => s.userId || s.guestId)
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api.getOrders(effectiveUserId)
      .then((res) => alive && setOrders(res.orders ?? []))
      .catch(() => alive && setOrders([]))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [effectiveUserId])

  return (
    <div className="aurora-bg flex h-full flex-col">
      <header className="glass-strong z-10 flex items-center gap-2 border-b border-[var(--line)] px-3 py-3">
        <button onClick={() => navigate(-1)} className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-soft transition hover:bg-[var(--surface-variant)]" aria-label="返回">
          <ArrowLeft size={20} />
        </button>
        <span className="font-semibold text-ink">我的订单</span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-8">
          <section className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-500">Order history</p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink">你的购买记录</h1>
              <p className="mt-1 text-sm text-ink-muted">订单状态、商品和金额都在这里。</p>
            </div>
            {!loading && orders.length > 0 && (
              <div className="inline-flex w-fit items-center gap-2 rounded-full border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-sm text-ink-soft shadow-sm">
                <ReceiptText size={15} className="text-brand-500" /> 共 {orders.length} 笔订单
              </div>
            )}
          </section>

          {loading ? <LoadingBlock text="正在整理你的订单…" /> : orders.length === 0 ? (
            <EmptyState icon={<ShoppingBag size={28} />} title="还没有订单" description="挑到喜欢的商品后，就会在这里留下记录。" action={<button onClick={() => navigate('/shop')} className="btn-primary mt-2">去逛逛</button>} />
          ) : (
            <div className="space-y-4">
              {orders.map((order) => {
                const visibleItems = order.items.slice(0, 3)
                const hiddenCount = Math.max(0, order.items.length - visibleItems.length)
                return (
                  <article key={order.order_id} className="glass overflow-hidden border border-[var(--card-border)] shadow-lift transition hover:-translate-y-0.5 hover:shadow-float">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-[var(--line)] px-4 py-3.5 sm:px-5">
                      <span className="font-mono text-xs text-ink-muted">{order.order_id}</span>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLE[order.status] ?? 'bg-[var(--surface-variant)] text-ink-soft'}`}>
                        <PackageCheck size={13} /> {STATUS_CN[order.status] ?? order.status}
                      </span>
                      <span className="ml-auto inline-flex items-center gap-1 text-xs text-ink-muted"><Clock3 size={13} /> {relativeTime(order.created_at)}</span>
                    </div>

                    <div className="divide-y divide-[var(--line)] px-4 sm:px-5">
                      {visibleItems.map((item, index) => (
                        <div key={`${item.product_id ?? item.title}-${index}`} className="flex items-center gap-3 py-3.5">
                          <ProductImage src={item.image_url} productId={item.product_id} alt={item.title} className="h-[76px] w-[76px] shrink-0 border border-[var(--line)]" rounded="rounded-2xl" />
                          <div className="min-w-0 flex-1">
                            <p className="line-clamp-2 text-sm font-semibold leading-snug text-ink">{item.title || '商品信息待补全'}</p>
                            <p className="mt-1 line-clamp-1 text-xs text-ink-muted">{[item.brand, item.sku_label].filter(Boolean).join(' · ') || '标准款'}</p>
                          </div>
                          <div className="shrink-0 text-right"><p className="text-sm font-semibold text-price">{formatPrice(item.price)}</p><p className="mt-1 text-xs text-ink-muted">x{item.quantity}</p></div>
                        </div>
                      ))}
                      {hiddenCount > 0 && <p className="py-3 text-sm text-ink-muted">另有 {hiddenCount} 件商品</p>}
                    </div>

                    <footer className="flex items-center justify-between gap-4 bg-[var(--surface-variant)]/45 px-4 py-3.5 sm:px-5">
                      <span className="text-sm text-ink-soft">{order.items.length} 件商品</span>
                      <div className="flex items-center gap-4"><span className="hidden text-xs text-ink-muted sm:inline">商品明细已展开</span><span className="text-sm text-ink-soft">实付 <strong className="ml-1 text-xl text-price">{formatPrice(order.total_price, 2)}</strong></span></div>
                    </footer>
                  </article>
                )
              })}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
