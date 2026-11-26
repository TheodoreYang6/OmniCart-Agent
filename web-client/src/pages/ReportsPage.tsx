import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { ArrowUpRight, FileText } from 'lucide-react'
import { reportPayments, type ReportOrder } from '@/api/reportPayments'
import { useAuthStore } from '@/store/authStore'

const money = (fen: number) => `¥${(fen / 100).toFixed(2)}`
const statusLabels = { quoted: '旧报价', pending: '历史支付待核实', paid: '已交付', closed: '已关闭', delivered: '已生成' }

function ReportContent({ order }: { order: ReportOrder }) {
  if (!order.report) return null
  return (
    <section className="mt-7 space-y-3" aria-label="已交付报告">
      <h2 className="text-xl font-bold text-ink">选购报告</h2>
      <p className="text-sm text-ink-muted">{order.report.limitations}</p>
      <div className="grid gap-3 xl:grid-cols-3">
        {order.report.products.map((product) => (
          <article key={product.product_id} className="glass min-w-0 space-y-3 p-5">
            <p className="text-sm font-semibold text-brand-600">{product.comparison_role}</p>
            <h3 className="font-semibold text-ink">{product.title}</h3>
            <p className="text-lg font-bold text-price">{money(product.price_fen)}</p>
            <p className="text-sm text-ink-muted">
              预算余量 {money(product.budget_left_fen)} · {product.average_rating === null
                ? '暂无评价样本' : `样本均分 ${product.average_rating} / 5（${product.review_count} 条）`}
            </p>
            {product.description && <p className="text-sm leading-relaxed text-ink-soft">{product.description}</p>}
            {product.faq.map((faq, i) => (
              <dl key={i} className="text-sm leading-relaxed">
                <dt className="font-medium text-ink">{faq.question}</dt>
                <dd className="text-ink-muted">{faq.answer}</dd>
              </dl>
            ))}
            {product.review && <blockquote className="border-l-2 border-brand-300 pl-3 text-sm text-ink-muted">{product.review}</blockquote>}
            <Link className="focus-ring inline-flex items-center gap-1 text-sm font-semibold text-brand-600" to={`/product/${encodeURIComponent(product.product_id)}`}>
              查看商品 <ArrowUpRight size={14} />
            </Link>
          </article>
        ))}
      </div>
    </section>
  )
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const orderId = params.get('order') ?? ''
  const returnedFromAlipay = params.get('return') === 'alipay'
  const refreshedOnReturn = useRef('')
  const channel = params.get('source') === 'agent' ? 'agent' : 'web'
  const location = useLocation()
  const userId = useAuthStore((state) => state.initialized ? state.userId : '')
  const queryClient = useQueryClient()
  const [category, setCategory] = useState('')
  const [budget, setBudget] = useState('')
  const service = useQuery({ queryKey: ['report-service'], queryFn: reportPayments.service, retry: false })
  const categories = useQuery({
    queryKey: ['report-categories'], queryFn: reportPayments.categories, enabled: service.data?.enabled === true, retry: false,
  })
  const history = useQuery({
    queryKey: ['report-orders', userId], queryFn: reportPayments.orders, enabled: Boolean(userId), retry: false,
  })
  const orderKey = ['report-order', userId, orderId]
  const selected = useQuery({
    queryKey: orderKey,
    queryFn: () => reportPayments.order(orderId),
    enabled: Boolean(userId && orderId),
    retry: false,
  })
  const order = selected.data
  const chooseOrder = (id: string) => {
    setParams((previous) => {
      const next = new URLSearchParams()
      if (id) next.set('order', id)
      if (previous.get('source') === 'agent') next.set('source', 'agent')
      return next
    })
  }

  const saveOrder = (data: ReportOrder) => {
    queryClient.setQueryData(['report-order', userId, data.order_id], data)
    void queryClient.invalidateQueries({ queryKey: ['report-orders', userId] })
  }
  const generate = useMutation({
    mutationFn: () => reportPayments.generate(category, Math.round(Number(budget) * 100), channel),
    onSuccess: (data) => {
      if (useAuthStore.getState().userId !== userId) return
      saveOrder(data)
      chooseOrder(data.order_id)
    },
  })
  const refresh = useMutation({
    mutationFn: reportPayments.refresh,
    onSuccess: (data) => {
      if (useAuthStore.getState().userId === userId) saveOrder(data)
    },
  })
  const { mutate: refreshOrder } = refresh
  const canRefresh = order && (order.mode === 'sandbox' || order.mode === 'production')
    && (order.status === 'pending' || order.status === 'closed')
  useEffect(() => {
    if (returnedFromAlipay && canRefresh && refreshedOnReturn.current !== orderId) {
      refreshedOnReturn.current = orderId
      refreshOrder(orderId)
    }
  }, [canRefresh, orderId, returnedFromAlipay, refreshOrder])
  const formError = generate.error ?? categories.error
  const historyError = (refresh.variables === orderId ? refresh.error : null) ?? selected.error
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    generate.mutate()
  }

  return (
    <div className="aurora-bg h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-7 flex items-start gap-4">
          <span className="glass grid size-12 shrink-0 place-items-center text-brand-600"><FileText size={23} /></span>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-ink">欧米选购报告</h1>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-muted">
              按品类和预算，从欧米商品库筛选 2–3 款候选，整理参考价格、常见问答和评价样本。可免费生成，登录后可在报告记录中重复查看。
            </p>
            <Link to="/chat" className="focus-ring mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand-600">
              去对话免费获取推荐 <ArrowUpRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </header>

        {service.isError && <p role="alert" className="mb-4 text-sm text-ink">暂时无法读取报告服务。</p>}
        {service.data && !service.data.enabled && <p className="mb-4 text-sm text-ink-muted">暂时无法生成新报告。</p>}
        {!userId && service.data?.enabled && (
          <Link to="/login" state={{ from: location.pathname + location.search }} className="btn-primary inline-flex">登录后生成报告</Link>
        )}
        {userId && (
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            {service.data?.enabled && (
              <section className="glass p-5 sm:p-6">
                <h2 className="mb-4 text-lg font-semibold text-ink">报告需求</h2>
                <form onSubmit={submit} className="grid gap-4">
                  <label className="grid gap-2 text-sm font-medium text-ink">
                    商品品类
                    <select required value={category} onChange={(event) => setCategory(event.target.value)} className="input-field">
                      <option value="">{categories.isPending ? '正在加载品类…' : '请选择品类'}</option>
                      {categories.data?.map((item) => <option key={item}>{item}</option>)}
                    </select>
                  </label>
                  <label className="grid gap-2 text-sm font-medium text-ink">
                    商品预算上限（元）
                    <input required type="number" min=".01" max="1000000" step=".01" placeholder="例如 500" value={budget} onChange={(event) => setBudget(event.target.value)} className="input-field" />
                  </label>
                  <button type="submit" className="btn-primary justify-self-start" disabled={generate.isPending || !category}>
                    {generate.isPending ? '正在生成…' : '免费生成报告'}
                  </button>
                  {formError && <p role="alert" className="text-sm text-ink">{formError.message}</p>}
                </form>
              </section>
            )}
            <section className="glass p-5 sm:p-6" aria-label="报告记录">
              <h2 className="text-lg font-semibold text-ink">报告记录</h2>
              {selected.isLoading && <p role="status" className="mt-3 text-sm text-ink-muted">正在读取报告…</p>}
              {order && (
                <div className="mt-3 space-y-3">
                  <p className="font-medium text-ink">{order.category} · {statusLabels[order.status]}</p>
                  <p className="text-sm text-ink-muted">
                    商品预算 {money(order.budget_fen)} · 共 {order.candidate_count} 款候选{order.channel === 'agent' ? ' · Agent 发起' : ''}
                  </p>
                  {order.status === 'paid' && order.trade_no && <p className="break-all text-sm text-ink-muted">历史交易号 {order.trade_no}</p>}
                  {canRefresh && (
                    <button className="btn-outline" disabled={refresh.isPending} onClick={() => refreshOrder(orderId)}>
                      核实历史付款
                    </button>
                  )}
                </div>
              )}
              {historyError && <p role="alert" className="mt-3 text-sm text-ink">{historyError.message}</p>}
              {history.isError && <p role="alert" className="mt-3 text-sm text-ink">暂时无法读取报告记录。</p>}
              {!orderId && !history.data?.length && !history.isPending && <p className="mt-3 text-sm text-ink-muted">暂无报告记录。</p>}
              {Boolean(history.data?.length) && (
                <ul className="mt-4 space-y-2 border-t border-[var(--line)] pt-3">
                  {history.data?.map((item) => (
                    <li key={item.order_id}>
                      <button className="focus-ring flex w-full justify-between gap-3 rounded-md px-2 py-1 text-left text-sm text-ink-soft hover:bg-brand-500/10" aria-current={item.order_id === orderId ? 'true' : undefined} onClick={() => chooseOrder(item.order_id)}>
                        <span>{item.category} · {statusLabels[order?.order_id === item.order_id ? order.status : item.status]}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
        {order && userId && <ReportContent order={order} />}
        {service.data?.skillpay_url && (
          <a className="focus-ring mt-6 inline-flex items-center gap-1 text-sm font-semibold text-brand-600" href={service.data.skillpay_url}>
            在支付宝 Skill Pay 获取欧米比价技能 <ArrowUpRight size={14} />
          </a>
        )}
      </div>
    </div>
  )
}
