import { useState } from 'react'
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
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Modal } from '@/components/ui/Modal'
import { ShopActionCard } from '@/components/chat/ShopActionCard'
import { useAuthStore } from '@/store/authStore'
import type { CartItem, CheckoutPreviewResponse, CheckoutSubmitResponse } from '@/api/types'

export function CartPage() {
  const navigate = useNavigate()
  const items = useCartStore((s) => s.items)
  const isLoading = useCartStore((s) => s.isLoading)
  const hasLoaded = useCartStore((s) => s.hasLoaded)
  const error = useCartStore((s) => s.error)
  const loadCart = useCartStore((s) => s.loadCart)
  const toggleItem = useCartStore((s) => s.toggleItem)
  const toggleSelectAll = useCartStore((s) => s.toggleSelectAll)
  const setQuantity = useCartStore((s) => s.setQuantity)
  const removeItem = useCartStore((s) => s.removeItem)
  const previewCheckout = useCartStore((s) => s.previewCheckout)
  const submitCheckout = useCartStore((s) => s.submitCheckout)
  const pendingIds = useCartStore((s) => s.pendingIds)
  const isSelectAllPending = useCartStore((s) => s.isSelectAllPending)
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())
  const [deleteTarget, setDeleteTarget] = useState<CartItem | null>(null)
  const [preview, setPreview] = useState<CheckoutPreviewResponse | null>(null)
  const [result, setResult] = useState<CheckoutSubmitResponse | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const selected = items.filter((i) => i.selected)
  const totalPrice = selected.reduce((sum, i) => sum + i.price * i.quantity, 0)
  const allSelected = items.length > 0 && items.every((i) => i.selected)

  // 场景③：下单完成 —— 欧米得意态瞬时浮层（1.6s 自动消失，不打断跳转）
  const [orderCheer, setOrderCheer] = useState(false)

  const handleCheckout = async () => {
    if (selected.length === 0) {
      toast.info('请先选择要结算的商品')
      return
    }
    if (!isLoggedIn) {
      toast.info('登录后即可结算，购物车会自动保留')
      navigate('/login', { state: { from: '/cart' } })
      return
    }
    const data = await previewCheckout()
    if (data) {
      setPreview(data)
    }
  }

  const confirmCheckout = async () => {
    setSubmitting(true)
    const data = await submitCheckout()
    setSubmitting(false)
    if (!data) return
    setPreview(null)
    setResult(data)
    setOrderCheer(true)
    toast.success('下单成功')
    setTimeout(() => setOrderCheer(false), 1600)
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
        <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 lg:py-6">
          {isLoading && !hasLoaded ? (
            <LoadingBlock text="加载购物车…" />
          ) : error && items.length === 0 ? (
            <EmptyState
              icon={<ShoppingCart size={28} />}
              title="购物车加载失败"
              description={error}
              action={
                <button onClick={() => void loadCart()} className="btn-primary mt-2">
                  重新加载
                </button>
              }
            />
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
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-2.5">
                {items.map((item) => (
                <div
                  key={item.cart_item_id}
                  className="glass card-hover flex items-center gap-3 p-3"
                >
                  <button
                    onClick={() => toggleItem(item.cart_item_id)}
                    disabled={pendingIds.includes(item.cart_item_id)}
                    aria-label={item.selected ? `取消选择 ${item.title}` : `选择 ${item.title}`}
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
                          onClick={() => setDeleteTarget(item)}
                          className="rounded-lg p-1.5 text-ink-muted transition hover:bg-rose-500/10 hover:text-rose-500"
                          aria-label={`从购物车删除 ${item.title}`}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                ))}
              </div>
              <aside className="sticky top-5 hidden rounded-[24px] border border-[var(--line)] bg-[var(--surface)] p-5 shadow-soft lg:block">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-500">Order summary</p>
                <h2 className="mt-1 text-lg font-bold text-ink">结算摘要</h2>
                <button
                  onClick={toggleSelectAll}
                  disabled={isSelectAllPending}
                  className="focus-ring mt-5 flex w-full items-center gap-2 rounded-xl py-2 text-sm text-ink-soft disabled:opacity-60"
                >
                  <SelectionMark selected={allSelected} /> 全选购物车商品
                </button>
                <div className="my-4 h-px bg-[var(--line)]" />
                <div className="flex items-center justify-between text-sm text-ink-muted"><span>已选商品</span><span>{selected.length} 件</span></div>
                <div className="mt-3 flex items-end justify-between"><span className="text-sm text-ink-muted">合计</span><strong className="text-2xl text-price">{formatPrice(totalPrice, 2)}</strong></div>
                <button onClick={handleCheckout} disabled={selected.length === 0} className="btn-primary mt-5 w-full py-3 disabled:opacity-50">结算 ({selected.length})</button>
                {!isLoggedIn && <p className="mt-3 text-xs leading-relaxed text-ink-muted">游客购物车会保留，登录后自动合并再结算。</p>}
              </aside>
            </div>
          )}
        </div>
      </div>

      {/* 结算栏 */}
      {items.length > 0 && (
        <div className="glass-strong border-t border-[var(--line)] px-4 py-3 lg:hidden">
          <div className="mx-auto flex max-w-3xl items-center gap-3">
            <button
              onClick={toggleSelectAll}
              disabled={isSelectAllPending}
              className="flex items-center gap-1.5 text-sm text-ink-soft"
            >
              <SelectionMark selected={allSelected} />
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
      <ConfirmDialog open={!!deleteTarget} title="移出购物车" description={`确定将“${deleteTarget?.title ?? ''}”移出购物车吗？`} onClose={() => setDeleteTarget(null)} onConfirm={async () => { if (!deleteTarget) return; await removeItem(deleteTarget.cart_item_id); setDeleteTarget(null) }} />

      {/* 结算确认弹窗 */}
      <Modal open={!!preview} onClose={() => setPreview(null)} title="确认订单" variant="center" className="sm:max-w-lg">
        {preview && (
          <div className="space-y-4">
            <ShopActionCard card={preview.shop_card} />
            {!preview.has_address && (
              <p className="text-sm text-amber-600 dark:text-amber-300">还没有收货地址，请先填写后再结算。</p>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setPreview(null); navigate('/address') }} className="rounded-xl border border-[var(--field-border)] px-4 py-2 text-sm text-ink-soft transition hover:bg-[var(--surface-variant)]">修改地址</button>
              <button
                onClick={confirmCheckout}
                disabled={submitting || !preview.has_address}
                className="btn-primary px-5 py-2 text-sm disabled:opacity-50"
              >
                {submitting ? '提交中…' : '确认下单'}
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* 下单结果弹窗 */}
      <Modal open={!!result} onClose={() => setResult(null)} title="下单成功" variant="center" className="sm:max-w-lg">
        {result && (
          <div className="space-y-4">
            <ShopActionCard card={result.shop_card} />
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">{result.answer || result.message}</p>
            <div className="flex justify-end">
              <button onClick={() => { setResult(null); navigate('/orders') }} className="btn-primary px-5 py-2 text-sm">查看订单</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

function SelectionMark({ selected }: { selected: boolean }) {
  return (
    <span className={cn('flex h-5 w-5 items-center justify-center rounded-full border-2 transition', selected ? 'gradient-brand border-transparent text-white shadow-glow' : 'border-[var(--field-border)]')}>
      {selected && <Check size={13} strokeWidth={3} />}
    </span>
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
        aria-label="减少数量"
      >
        <Minus size={14} />
      </button>
      <span className="w-8 text-center text-sm font-medium text-ink">{value}</span>
      <button
        onClick={onInc}
        disabled={value >= 99}
        className="flex h-7 w-7 items-center justify-center text-ink-muted transition hover:bg-[var(--surface-variant)]"
        aria-label="增加数量"
      >
        <Plus size={14} />
      </button>
    </div>
  )
}
