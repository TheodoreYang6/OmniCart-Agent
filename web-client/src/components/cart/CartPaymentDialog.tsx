import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, FlaskConical, MapPin } from 'lucide-react'
import { alipayCheckoutUrl, cartPayments, type CartPayment } from '@/api/cartPayments'
import { Modal } from '@/components/ui/Modal'
import { formatPrice } from '@/lib/utils'
import { useAuthStore } from '@/store/authStore'
import { useCartStore } from '@/store/cartStore'
import { toast } from '@/store/toastStore'

const labels = { quoted: '待确认', pending: '待付款', paid: '支付成功', closed: '已关闭', refunded: '已退款', partially_refunded: '部分退款' }

export function CartPaymentDialog({ orderId, returned, onClose }: {
  orderId: string
  returned: boolean
  onClose: () => void
}) {
  const userId = useAuthStore((state) => state.userId)
  const loadCart = useCartStore((state) => state.loadCart)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const verifiedOnReturn = useRef(false)
  const [confirmingCancel, setConfirmingCancel] = useState(false)
  const queryKey = ['cart-payment', userId, orderId]
  const orderQuery = useQuery({
    queryKey, queryFn: () => cartPayments.get(orderId), retry: false,
    refetchInterval: (query) => query.state.data?.status === 'pending' ? 5000 : false,
  })
  const order = orderQuery.data
  const hideCancelledOrder = Boolean(order?.cancel_requested && (order.status === 'pending' || order.status === 'closed'))
  const canRefresh = Boolean(order && !hideCancelledOrder && order.mode !== 'demo'
    && (order.status === 'pending' || order.status === 'closed'))
  useEffect(() => {
    if (hideCancelledOrder) onClose()
  }, [hideCancelledOrder, onClose])
  const operation = useMutation({
    mutationFn: (method: 'confirm' | 'refresh' | 'demoPay' | 'cancel') => cartPayments[method](orderId),
    onSuccess: (data, method) => {
      if (useAuthStore.getState().userId !== userId) return
      queryClient.setQueryData(queryKey, data)
      if (method === 'cancel' && (data.status === 'closed' || (data.status === 'pending' && data.cancel_requested))) {
        queryClient.setQueryData<CartPayment | null>(['active-cart-payment', userId], (active) =>
          active?.order_id === orderId ? null : active,
        )
        if (data.status === 'closed') toast.success('订单已取消，商品已保留')
        else toast.info('已申请取消，可以先结算其他商品')
        if (!data.cancel_requested) onClose()
      } else if (method === 'cancel') {
        toast.info('该订单已有付款记录，请查看交易结果')
      }
      void queryClient.invalidateQueries({ queryKey: ['active-cart-payment', userId] })
      const url = alipayCheckoutUrl(data.checkout_url)
      if (url) window.location.assign(url)
    },
  })
  const { mutate } = operation
  useEffect(() => {
    if (returned && canRefresh && !verifiedOnReturn.current) {
      verifiedOnReturn.current = true
      mutate('refresh')
    }
  }, [mutate, canRefresh, returned])
  const isPaid = order?.status === 'paid'
  const canConfirm = order && !order.expired
    && (order.status === 'quoted' || (order.status === 'pending' && order.mode !== 'demo'))
  const canDemoPay = order && !order.expired && order.status === 'pending' && order.mode === 'demo'
  const canCancel = order?.status === 'quoted' || order?.status === 'pending'
  const canRequote = order?.status === 'closed'
    || (order?.expired && (order.status === 'quoted' || (order.status === 'pending' && order.mode === 'demo')))
  const address = order?.address
  const addressLines = address ? [
    [address.name, address.phone].filter(Boolean).join(' · '),
    [address.province, address.city, address.district, address.detail].filter(Boolean).join(' '),
  ] : []
  const error = operation.error || orderQuery.error
  useEffect(() => {
    if (isPaid) {
      void loadCart()
      void queryClient.invalidateQueries({ queryKey: ['active-cart-payment', userId] })
    }
  }, [isPaid, loadCart, queryClient, userId])

  if (hideCancelledOrder) return null

  return (
    <Modal open onClose={onClose} title="支付宝支付" variant="bottom" className="sm:max-w-xl">
      <div className="space-y-4 px-5 py-4 sm:px-6">
        {orderQuery.isPending && <p role="status" className="text-sm text-ink-muted">正在读取支付订单…</p>}
        {order && (
          <>
            <div className="rounded-2xl bg-[var(--surface-variant)] p-4">
              <div role="status" className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                <div>
                  <p className="text-sm text-ink-muted">{isPaid ? '已付金额' : '订单金额'}</p>
                  <p className="mt-1 text-3xl font-bold tracking-tight text-ink tabular-nums">
                    {formatPrice(order.amount_fen / 100, 2)}
                  </p>
                </div>
                <span className="rounded-full bg-[var(--surface)] px-3 py-1 text-xs font-medium text-ink-soft">
                  {labels[order.status]}
                </span>
              </div>
              {order.mode !== 'production' && (
                <p className="mt-3 flex items-center gap-2 text-xs text-ink-soft">
                  <FlaskConical size={15} aria-hidden="true" />
                  {order.mode === 'sandbox' ? '支付宝沙箱 · 使用测试账号，无实际扣款' : '本地演示 · 无实际扣款'}
                </p>
              )}
            </div>
            <section aria-label="商品和收货信息" className="rounded-2xl border border-[var(--line)] px-4">
              <h4 className="pt-3 text-sm font-semibold text-ink">商品明细</h4>
              <ul className="divide-y divide-[var(--line)]">
                {order.items.map((item, index) => (
                  <li key={index} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 py-3 text-sm">
                    <div className="min-w-0">
                      <p className="break-words font-medium text-ink">{item.title}</p>
                      <p className="mt-1 text-xs text-ink-muted">
                        {item.sku_label && `${item.sku_label} · `}×{item.quantity}
                      </p>
                    </div>
                    <span className="whitespace-nowrap font-semibold text-ink tabular-nums">
                      {formatPrice(item.price * item.quantity, 2)}
                    </span>
                  </li>
                ))}
              </ul>
              {address && (
                <div className="flex items-start gap-2 border-t border-[var(--line)] py-3">
                  <MapPin size={16} className="mt-0.5 shrink-0 text-ink-muted" aria-hidden="true" />
                  <div className="min-w-0 space-y-1 break-words text-xs text-ink-muted">
                    <h4 className="text-sm font-semibold text-ink">收货地址</h4>
                    {addressLines.filter(Boolean).map((line, index) => <p key={index}>{line}</p>)}
                  </div>
                </div>
              )}
            </section>
            {order.expired && !isPaid && <p className="text-sm text-ink-muted">支付链接已过期。若已付款，请先查询结果。</p>}
            {order.refunded_fen > 0 && <p className="text-sm text-ink-muted">已退款 {formatPrice(order.refunded_fen / 100, 2)}</p>}
            {isPaid && order.trade_no && <p className="break-all text-sm text-ink-muted">交易号 {order.trade_no}</p>}
            {order.expired && order.status === 'pending' && order.mode !== 'demo' && (
              <p className="text-sm text-ink-muted">支付宝确认旧订单状态后，才能重新结算。</p>
            )}
          </>
        )}
        {error && <p role="alert" className="text-sm text-ink-soft">{error.message}</p>}
      </div>
      {order && (canConfirm || canDemoPay || isPaid || canRequote || canRefresh || canCancel) && (
        <div className="sticky bottom-0 flex flex-col gap-2 border-t border-[var(--line)] bg-[var(--surface)] px-5 py-4 text-sm sm:flex-row sm:flex-wrap sm:justify-end sm:px-6">
          {canCancel && confirmingCancel ? (
            <>
              <p className="self-center text-ink-soft sm:mr-auto">取消这笔订单？商品会保留在购物车。</p>
              <button className="btn-outline focus-ring" onClick={() => setConfirmingCancel(false)}>保留订单</button>
              <button className="btn-primary focus-ring" onClick={() => {
                setConfirmingCancel(false)
                mutate('cancel')
              }}>确认取消</button>
            </>
          ) : (
            <>
              {canCancel && (
                <button className="btn-outline focus-ring disabled:opacity-50 sm:mr-auto" disabled={operation.isPending}
                  onClick={() => setConfirmingCancel(true)}>
                  {operation.isPending && operation.variables === 'cancel' ? '正在取消…' : '取消订单'}
                </button>
              )}
              {canConfirm && (
                <button className="btn-primary focus-ring" disabled={operation.isPending} onClick={() => mutate('confirm')}>
                  {order.mode === 'demo' ? '确认演示支付' : <>确认并前往支付宝 <ArrowUpRight size={16} aria-hidden="true" /></>}
                </button>
              )}
              {canDemoPay && (
                <button className="btn-primary focus-ring" disabled={operation.isPending} onClick={() => mutate('demoPay')}>模拟付款成功</button>
              )}
              {isPaid && <button className="btn-primary focus-ring" onClick={() => navigate('/orders')}>查看购物订单</button>}
              {canRequote && (
                <button className="btn-primary focus-ring" onClick={() => navigate('/cart', { replace: true })}>
                  返回购物车重新结算
                </button>
              )}
              {canRefresh && (
                <button className="btn-outline focus-ring disabled:opacity-50" disabled={operation.isPending} onClick={() => mutate('refresh')}>
                  {operation.isPending && operation.variables === 'refresh' ? '正在查询…' : '查询支付结果'}
                </button>
              )}
              {order.status === 'quoted' && !order.expired && (
                <button className="btn-outline focus-ring" onClick={() => navigate('/address')}>修改收货地址</button>
              )}
            </>
          )}
        </div>
      )}
    </Modal>
  )
}
