import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, PackageCheck, Receipt } from 'lucide-react'
import { api } from '@/api/client'
import type { Order } from '@/api/types'
import { ProductImage } from '@/components/ui/ProductImage'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingBlock } from '@/components/ui/Spinner'
import { useAuthStore } from '@/store/authStore'
import { formatPrice, relativeTime } from '@/lib/utils'

const STATUS_CN: Record<string, string> = {
  pending: '待发货',
  paid: '已支付',
  shipped: '已发货',
  completed: '已完成',
  cancelled: '已取消',
}

export function OrdersPage() {
  const navigate = useNavigate()
  const effectiveUserId = useAuthStore((s) => s.userId || s.guestId)
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .getOrders(effectiveUserId)
      .then((res) => alive && setOrders(res.orders ?? []))
      .catch(() => alive && setOrders([]))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [effectiveUserId])

  return (
    <div className="aurora-bg flex h-full flex-col">
      <header className="glass-strong z-10 flex items-center gap-2 border-b border-[var(--line)] px-3 py-3">
        <button
          onClick={() => navigate(-1)}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-soft transition hover:bg-[var(--surface-variant)]"
        >
          <ArrowLeft size={20} />
        </button>
        <span className="font-medium text-ink">我的订单</span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6">
          {loading ? (
            <LoadingBlock text="加载订单…" />
          ) : orders.length === 0 ? (
            <EmptyState
              icon={<Receipt size={28} />}
              title="还没有订单"
              description="下单后可在这里查看"
            />
          ) : (
            <div className="relative grid items-start gap-4 lg:grid-cols-2 lg:before:absolute lg:before:-left-7 lg:before:top-2 lg:before:h-[calc(100%-1rem)] lg:before:w-px lg:before:bg-[var(--line)]">
              {orders.map((order) => (
                <div
                  key={order.order_id}
                  className="glass card-hover p-4"
                >
                  <div className="flex items-center justify-between border-b border-[var(--line)] pb-2.5">
                    <span className="font-mono text-xs text-ink-muted">{order.order_id}</span>
                    <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                      <PackageCheck size={13} />
                      {STATUS_CN[order.status] ?? order.status}
                    </span>
                  </div>

                  <div className="space-y-2.5 py-3">
                    {order.items.map((it, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <ProductImage
                          src={it.image_url}
                          alt={it.title}
                          className="h-14 w-14 shrink-0"
                          rounded="rounded-lg"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-1 text-sm font-medium text-ink">{it.title}</p>
                          <p className="text-xs text-ink-muted">
                            {it.sku_label && `${it.sku_label} · `}x{it.quantity}
                          </p>
                        </div>
                        <span className="text-sm text-price">{formatPrice(it.price)}</span>
                      </div>
                    ))}
                  </div>

                  <div className="flex items-center justify-between border-t border-[var(--line)] pt-2.5">
                    <span className="text-xs text-ink-muted">
                      {relativeTime(order.created_at)}
                    </span>
                    <span className="text-sm">
                      合计{' '}
                      <span className="text-lg font-bold text-price">
                        {formatPrice(order.total_price, 2)}
                      </span>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
