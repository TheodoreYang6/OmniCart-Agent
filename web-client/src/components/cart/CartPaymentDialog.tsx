import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { alipayCheckoutUrl, cartPayments } from '@/api/cartPayments'
import { ShopActionCard } from '@/components/chat/ShopActionCard'
import { Modal } from '@/components/ui/Modal'
import { useAuthStore } from '@/store/authStore'
import { useCartStore } from '@/store/cartStore'

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
  const queryKey = ['cart-payment', userId, orderId]
  const orderQuery = useQuery({
    queryKey, queryFn: () => cartPayments.get(orderId), retry: false,
    refetchInterval: (query) => query.state.data?.status === 'pending' ? 5000 : false,
  })
  const order = orderQuery.data
  const operation = useMutation({
    mutationFn: (method: 'confirm' | 'refresh' | 'demoPay') => cartPayments[method](orderId),
    onSuccess: (data) => {
      if (useAuthStore.getState().userId !== userId) return
      queryClient.setQueryData(queryKey, data)
      void queryClient.invalidateQueries({ queryKey: ['active-cart-payment', userId] })
      const url = alipayCheckoutUrl(data.checkout_url)
      if (url) window.location.assign(url)
    },
  })
  const { mutate } = operation
  useEffect(() => {
    if (returned && order?.status === 'pending' && order.mode !== 'demo' && !verifiedOnReturn.current) {
      verifiedOnReturn.current = true
      mutate('refresh')
    }
  }, [mutate, order, returned])
  const isPaid = order?.status === 'paid'
  useEffect(() => {
    if (isPaid) {
      void loadCart()
      void queryClient.invalidateQueries({ queryKey: ['active-cart-payment', userId] })
    }
  }, [isPaid, loadCart, queryClient, userId])

  return (
    <Modal open onClose={onClose} title="支付宝支付" variant="center" className="sm:max-w-lg">
      <div className="space-y-3">
        {orderQuery.isPending && <p role="status">正在读取支付订单…</p>}
        {order && (
          <>
            <div role="status" className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-ink">{labels[order.status]}</span>
              <span className="text-xl font-bold text-price">¥{(order.amount_fen / 100).toFixed(2)}</span>
            </div>
            {order.mode === 'demo' && <p className="text-sm text-ink-muted">本地演示 · 无真实扣款</p>}
            {order.mode === 'sandbox' && <p className="text-sm text-ink-muted">支付宝沙箱 · 无真实扣款</p>}
            <ShopActionCard card={{ kind: 'order_preview', payload: {
              items: order.items, address: order.address, has_address: true, total: order.amount_fen / 100,
            } }} />
            {order.expired && !isPaid && <p className="text-sm text-ink-muted">支付链接已过期。若已付款，请先查询结果。</p>}
            {order.refunded_fen > 0 && <p className="text-sm text-ink-muted">已退款 ¥{(order.refunded_fen / 100).toFixed(2)}</p>}
            {isPaid && order.trade_no && <p className="break-all text-sm text-ink-muted">交易号 {order.trade_no}</p>}
            <div className="flex flex-wrap justify-end gap-2">
              {!order.expired && (order.status === 'quoted' || (order.status === 'pending' && order.mode !== 'demo')) && (
                <button className="btn-primary" disabled={operation.isPending} onClick={() => mutate('confirm')}>
                  {order.mode === 'demo' ? '确认演示支付' : '确认并前往支付宝'}
                </button>
              )}
              {!order.expired && order.status === 'pending' && order.mode === 'demo' && (
                <button className="btn-primary" disabled={operation.isPending} onClick={() => mutate('demoPay')}>模拟付款成功</button>
              )}
              {order.status === 'pending' && order.mode !== 'demo' && (
                <button className="btn-secondary" disabled={operation.isPending} onClick={() => mutate('refresh')}>查询支付结果</button>
              )}
              {isPaid && <button className="btn-primary" onClick={() => navigate('/orders')}>查看购物订单</button>}
              {!isPaid && order.status === 'quoted' && !order.expired && (
                <button className="btn-secondary" onClick={() => navigate('/address')}>修改收货地址</button>
              )}
              {/* 过期或已关闭时提供重新报价和查询结果出口，避免用户卡在弹窗里 */}
              {!isPaid && (order.expired || order.status === 'closed') && (
                <>
                  {order.status === 'pending' && (
                    <button className="btn-secondary" disabled={operation.isPending} onClick={() => mutate('refresh')}>
                      查询支付结果
                    </button>
                  )}
                  <button className="btn-primary" onClick={() => navigate('/cart', { replace: true })}>
                    返回购物车重新结算
                  </button>
                </>
              )}
            </div>
          </>
        )}
        {(operation.error || orderQuery.error) && <p role="alert" className="text-sm text-ink-soft">{(operation.error || orderQuery.error)?.message}</p>}
      </div>
    </Modal>
  )
}
