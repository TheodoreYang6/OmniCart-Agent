import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Minus, Plus, ShoppingCart, Trash2 } from 'lucide-react'
import { useCartStore } from '@/store/cartStore'
import { Omi } from '@/components/brand/Omi'
import { ProductImage } from '@/components/ui/ProductImage'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingBlock } from '@/components/ui/Spinner'
import { toast } from '@/store/toastStore'
import { formatPrice } from '@/lib/utils'
import { cn } from '@/lib/utils'

export function CartPage() {
  const navigate = useNavigate()
  const items = useCartStore((s) => s.items)
  const isLoading = useCartStore((s) => s.isLoading)
  const loadCart = useCartStore((s) => s.loadCart)
  const toggleItem = useCartStore((s) => s.toggleItem)
  const toggleSelectAll = useCartStore((s) => s.toggleSelectAll)
  const setQuantity = useCartStore((s) => s.setQuantity)
  const removeItem = useCartStore((s) => s.removeItem)
  const checkout = useCartStore((s) => s.checkout)
  const checkoutMessage = useCartStore((s) => s.checkoutMessage)
  const dismissCheckout = useCartStore((s) => s.dismissCheckoutMessage)

  const selected = items.filter((i) => i.selected)
  const totalPrice = selected.reduce((sum, i) => sum + i.price * i.quantity, 0)
  const allSelected = items.length > 0 && items.every((i) => i.selected)

  useEffect(() => {
    loadCart()
  }, [loadCart])

  // 场景③：下单完成 —— 欧米得意态瞬时浮层（1.6s 自动消失，不打断跳转）
  const [orderCheer, setOrderCheer] = useState(false)

  useEffect(() => {
    if (checkoutMessage) {
      setOrderCheer(true)
      const t = setTimeout(() => setOrderCheer(false), 1600)
      toast.success('下单成功')
      return () => clearTimeout(t)
    }
  }, [checkoutMessage])

  const handleCheckout = async () => {
    if (selected.length === 0) {
      toast.info('请先选择要结算的商品')
      return
    }
    const msg = await checkout()
    if (msg) {
      setTimeout(() => {
        dismissCheckout()
        navigate('/orders')
      }, 800)
    }
  }

  return (
    <div className="aurora-bg flex h-full flex-col">
      {/* 场景③：下单成功的欧米得意态——只露一下就走，不拦住用户 */}
      {orderCheer && (
        <div className="pointer-events-none fixed inset-x-0 top-24 z-50 flex justify-center animate-slide-up">
          <div className="glass-strong flex items-center gap-2 rounded-2xl px-4 py-2.5 shadow-lift">
            <Omi size={40} expression="smug" phase="talking" />
            <span className="text-sm font-semibold text-ink">下单成功啦喵～</span>
          </div>
        </div>
      )}

      <header className="glass-strong hidden items-center justify-between border-b border-[var(--line)] px-5 py-4 lg:flex">
        <h1 className="text-lg font-bold text-ink">购物车</h1>
        {items.length > 0 && <span className="text-sm text-ink-muted">{items.length} 件商品</span>}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 py-4">
          {isLoading ? (
            <LoadingBlock text="加载购物车…" />
          ) : items.length === 0 ? (
            <EmptyState
              icon={<ShoppingCart size={28} />}
              title="购物车还是空的"
              description="快去挑选心仪的好物吧"
              action={
                <button onClick={() => navigate('/shop')} className="btn-primary mt-2">
                  去逛逛
                </button>
              }
            />
          ) : (
            <div className="space-y-2.5">
              {items.map((item) => (
                <div
                  key={item.cart_item_id}
                  className="glass card-hover flex items-center gap-3 p-3"
                >
                  <button
                    onClick={() => toggleItem(item.cart_item_id)}
                    className={cn(
                      'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition',
                      item.selected
                        ? 'gradient-brand border-transparent text-white shadow-glow'
                        : 'border-[var(--field-border)]',
                    )}
                  >
                    {item.selected && <Check size={13} strokeWidth={3} />}
                  </button>

                  <ProductImage
                    src={item.image_url}
                    alt={item.title}
                    className="h-20 w-20 shrink-0"
                    rounded="rounded-xl"
                  />

                  <div className="flex min-w-0 flex-1 flex-col self-stretch">
                    <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">
                      {item.title}
                    </p>
                    {item.sku_label && (
                      <span className="mt-0.5 w-fit rounded bg-[var(--surface-variant)] px-1.5 py-0.5 text-[11px] text-ink-muted">
                        {item.sku_label}
                      </span>
                    )}
                    <div className="mt-auto flex items-center justify-between pt-1">
                      <span className="font-bold text-price">{formatPrice(item.price)}</span>
                      <div className="flex items-center gap-2">
                        <Stepper
                          value={item.quantity}
                          onDec={() => setQuantity(item.cart_item_id, item.quantity - 1)}
                          onInc={() => setQuantity(item.cart_item_id, item.quantity + 1)}
                        />
                        <button
                          onClick={() => removeItem(item.cart_item_id)}
                          className="rounded-lg p-1.5 text-ink-muted transition hover:bg-rose-500/10 hover:text-rose-500"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 结算栏 */}
      {items.length > 0 && (
        <div className="glass-strong border-t border-[var(--line)] px-4 py-3">
          <div className="mx-auto flex max-w-3xl items-center gap-3">
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-1.5 text-sm text-ink-soft"
            >
              <span
                className={cn(
                  'flex h-5 w-5 items-center justify-center rounded-full border-2 transition',
                  allSelected ? 'gradient-brand border-transparent text-white shadow-glow' : 'border-[var(--field-border)]',
                )}
              >
                {allSelected && <Check size={13} strokeWidth={3} />}
              </span>
              全选
            </button>
            <div className="ml-auto text-right">
              <p className="text-xs text-ink-muted">已选 {selected.length} 件</p>
              <p className="text-lg font-bold text-price">{formatPrice(totalPrice, 2)}</p>
            </div>
            <button
              onClick={handleCheckout}
              disabled={selected.length === 0}
              className="btn-primary px-6 py-3 disabled:opacity-50"
            >
              结算 ({selected.length})
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Stepper({
  value,
  onInc,
  onDec,
}: {
  value: number
  onInc: () => void
  onDec: () => void
}) {
  return (
    <div className="flex items-center overflow-hidden rounded-lg border border-[var(--field-border)]">
      <button
        onClick={onDec}
        disabled={value <= 1}
        className="flex h-7 w-7 items-center justify-center text-ink-muted transition hover:bg-[var(--surface-variant)] disabled:opacity-30"
      >
        <Minus size={14} />
      </button>
      <span className="w-8 text-center text-sm font-medium text-ink">{value}</span>
      <button
        onClick={onInc}
        className="flex h-7 w-7 items-center justify-center text-ink-muted transition hover:bg-[var(--surface-variant)]"
      >
        <Plus size={14} />
      </button>
    </div>
  )
}
