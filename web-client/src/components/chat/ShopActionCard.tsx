import { Minus, Plus, Repeat, Trash2 } from 'lucide-react'
import type { ChatAction, ShopCard } from '@/api/types'
import { ProductImage } from '@/components/ui/ProductImage'
import { formatPrice } from '@/lib/utils'

interface ShopActionCardProps {
  card: ShopCard
  onActionClick?: (action: ChatAction) => void
}

export function ShopActionCard({ card, onActionClick }: ShopActionCardProps) {
  if (card.kind === 'sku_picker') {
    const payload = card.payload
    return (
      <div className="glass rounded-2xl p-3">
        <div className="flex items-center gap-3">
          <ProductImage
            src={payload.image_url}
            productId={payload.product_id}
            alt={payload.title}
            className="h-16 w-16 shrink-0"
          />
          <div className="min-w-0">
            <p className="text-xs text-ink-muted">{payload.brand}</p>
            <p className="line-clamp-1 text-sm font-semibold text-ink">{payload.title}</p>
            <p className="mt-1 text-xs text-ink-soft">请选择规格</p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {payload.skus.map((sku) => (
            <button
              key={sku.sku_id}
              type="button"
              onClick={() =>
                onActionClick?.({
                  type: 'sku_option',
                  product_id: payload.product_id,
                  sku_id: sku.sku_id,
                  label: sku.label,
                })
              }
              className="flex items-center gap-1.5 rounded-xl border border-[var(--field-border)] bg-[var(--surface)] px-3 py-2 text-xs text-ink transition hover:border-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10"
            >
              <span>{sku.label}</span>
              <span className="font-semibold text-price">{formatPrice(sku.price)}</span>
            </button>
          ))}
        </div>
      </div>
    )
  }

  if (card.kind === 'cart_summary') {
    const payload = card.payload
    return (
      <div className="glass rounded-2xl p-3">
        <div className="space-y-2.5">
          {payload.items.map((item) => (
            <div
              key={item.cart_item_id || item.product_id}
              className="flex items-center gap-3 rounded-xl bg-[var(--surface-sunken)]/60 p-2.5"
            >
              <ProductImage
                src={item.image_url}
                productId={item.product_id}
                alt={item.title}
                className="h-14 w-14 shrink-0"
              />
              <div className="min-w-0 flex-1">
                <p className="line-clamp-1 text-sm font-medium text-ink">
                  {item.brand} {item.title}
                </p>
                {item.sku_label ? (
                  <p className="mt-0.5 line-clamp-1 text-[11px] text-ink-muted">{item.sku_label}</p>
                ) : null}
                <p className="mt-0.5 text-xs text-price">{formatPrice(item.price)}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-label="减少数量"
                    onClick={() =>
                      onActionClick?.({
                        type: 'cart_qty',
                        cart_item_id: item.cart_item_id,
                        quantity: item.quantity - 1,
                      })
                    }
                    className="flex h-6 w-6 items-center justify-center rounded-md border border-[var(--field-border)] text-ink-muted transition hover:bg-[var(--surface-variant)]"
                  >
                    <Minus size={12} />
                  </button>
                  <span className="w-6 text-center text-xs font-medium text-ink">{item.quantity}</span>
                  <button
                    type="button"
                    aria-label="增加数量"
                    onClick={() =>
                      onActionClick?.({
                        type: 'cart_qty',
                        cart_item_id: item.cart_item_id,
                        quantity: item.quantity + 1,
                      })
                    }
                    className="flex h-6 w-6 items-center justify-center rounded-md border border-[var(--field-border)] text-ink-muted transition hover:bg-[var(--surface-variant)]"
                  >
                    <Plus size={12} />
                  </button>
                </div>
                <div className="flex items-center gap-1.5">
                  {(item.skus?.length ?? 0) > 1 && (
                    <button
                      type="button"
                      onClick={() =>
                        onActionClick?.({ type: 'sku_reselect', cart_item_id: item.cart_item_id, product_id: item.product_id })
                      }
                      className="flex items-center gap-0.5 text-[11px] text-brand-600 hover:underline"
                    >
                      <Repeat size={11} />
                      重选规格
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label="删除"
                    onClick={() => onActionClick?.({ type: 'cart_remove', cart_item_id: item.cart_item_id })}
                    className="flex items-center gap-0.5 text-[11px] text-rose-500 hover:underline"
                  >
                    <Trash2 size={11} />
                    删除
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between border-t border-[var(--line)] pt-2 text-xs text-ink-soft">
          <span>共 {payload.count} 件</span>
          <span className="font-semibold text-price">合计 {formatPrice(payload.total)}</span>
        </div>
      </div>
    )
  }

  if (card.kind === 'order_preview') {
    const payload = card.payload
    return (
      <div className="glass rounded-2xl p-3">
        <div className="space-y-1.5">
          {payload.items.map((item, i) => (
            <div key={i} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 truncate text-ink">
                {item.brand} {item.title}
              </span>
              <span className="text-ink-muted">x{item.quantity}</span>
              <span className="text-price">{formatPrice(item.price * item.quantity)}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between border-t border-[var(--line)] pt-2 text-xs text-ink-soft">
          <span>合计</span>
          <span className="font-semibold text-price">{formatPrice(payload.total)}</span>
        </div>
        {payload.has_address && payload.address ? (
          <p className="mt-1 text-[11px] text-ink-muted">
            收货地址：{String(payload.address.name ?? '')} {String(payload.address.phone ?? '')}{' '}
            {String(payload.address.province ?? '')}
            {String(payload.address.city ?? '')}
            {String(payload.address.district ?? '')} {String(payload.address.detail ?? '')}
          </p>
        ) : (
          <p className="mt-1 text-[11px] text-ink-muted">尚未填写收货地址</p>
        )}
      </div>
    )
  }

  if (card.kind === 'order_created') {
    const payload = card.payload
    return (
      <div className="glass rounded-2xl p-3">
        <p className="text-sm font-semibold text-ink">订单 {payload.order_id}</p>
        <div className="mt-2 space-y-1">
          {payload.items.map((item, i) => (
            <div key={i} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 truncate text-ink">
                {item.brand} {item.title}
              </span>
              <span className="text-ink-muted">x{item.quantity}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between border-t border-[var(--line)] pt-2 text-xs text-ink-soft">
          <span>合计</span>
          <span className="font-semibold text-price">{formatPrice(payload.total)}</span>
        </div>
        <p className="mt-1 text-[11px] text-ink-muted">预计 {payload.eta}</p>
      </div>
    )
  }

  return null
}
