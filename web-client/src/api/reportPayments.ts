import { request } from './client'

export interface ReportService {
  title: string
  description: string
  amount_fen: number
  mode: 'free'
  enabled: boolean
  skillpay_url: string | null
}

interface ReportProduct {
  product_id: string
  title: string
  price_fen: number
  budget_left_fen: number
  average_rating: number | null
  review_count: number
  comparison_role: string
  description: string
  faq: { question: string; answer: string }[]
  review: string
}

export interface ReportOrder {
  order_id: string
  title: string
  category: string
  budget_fen: number
  candidate_count: number
  amount_fen: number
  channel: 'web' | 'agent'
  mode: 'free' | 'demo' | 'sandbox' | 'production'
  status: 'quoted' | 'pending' | 'paid' | 'closed' | 'delivered'
  created_at: string
  expires_at: string
  expired: boolean
  paid_at: string | null
  trade_no: string | null
  report: { products: ReportProduct[]; limitations: string } | null
}

const base = '/api/report-payments'
const orderPath = (id: string) => `${base}/orders/${encodeURIComponent(id)}`

export const reportPayments = {
  service: () => request<ReportService>(`${base}/service`),
  categories: () => request<string[]>(`${base}/categories`),
  generate: (category: string, budget_fen: number, channel: ReportOrder['channel']) =>
    request<ReportOrder>(`${base}/orders`, { method: 'POST', body: { category, budget_fen, channel } }),
  orders: () => request<ReportOrder[]>(`${base}/orders`),
  order: (id: string) => request<ReportOrder>(orderPath(id)),
  refresh: (id: string) => request<ReportOrder>(`${orderPath(id)}/refresh`, { method: 'POST' }),
}
