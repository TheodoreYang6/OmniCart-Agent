import { request } from './client'
import type { OrderPreviewPayload } from './types'

export interface CartPayment {
  order_id: string
  amount_fen: number
  status: 'quoted' | 'pending' | 'paid' | 'closed' | 'refunded' | 'partially_refunded'
  refunded_fen: number
  mode: 'demo' | 'sandbox' | 'production'
  expired: boolean
  trade_no: string | null
  checkout_url?: string | null
  items: OrderPreviewPayload['items']
  address: OrderPreviewPayload['address']
}

const base = '/api/cart-payments'
const path = (id: string) => `${base}/orders/${encodeURIComponent(id)}`
const confirmed = { method: 'POST', body: { confirmed: true } }

export const cartPayments = {
  service: () => request<{ enabled: boolean }>(`${base}/service`),
  active: () => request<CartPayment | null>(`${base}/active`),
  quote: (item_ids: string[]) => request<CartPayment>(`${base}/orders`, { method: 'POST', body: { item_ids } }),
  get: (id: string) => request<CartPayment>(path(id)),
  confirm: (id: string) => request<CartPayment>(`${path(id)}/confirm`, confirmed),
  refresh: (id: string) => request<CartPayment>(`${path(id)}/refresh`, { method: 'POST' }),
  demoPay: (id: string) => request<CartPayment>(`${path(id)}/demo-pay`, confirmed),
}

export function alipayCheckoutUrl(value?: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    if (
      (url.origin === 'https://openapi.alipay.com' || url.origin === 'https://openapi-sandbox.dl.alipaydev.com')
      && url.pathname === '/gateway.do' && !url.username && !url.password
    ) return value
  } catch {
    return null
  }
  return null
}
