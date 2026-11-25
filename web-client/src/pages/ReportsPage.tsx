import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { ArrowUpRight, FileText, ShieldCheck } from 'lucide-react'
import { reportPayments, type ReportOrder } from '@/api/reportPayments'
import { useAuthStore } from '@/store/authStore'

const money = (fen: number) => `¥${(fen / 100).toFixed(2)}`
const statusLabels = { quoted: '待确认', pending: '待付款', paid: '已交付', closed: '已关闭' }
const modeLabels = { demo: '本地演示 · 无真实扣款', sandbox: '支付宝沙箱 · 无真实扣款' }

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
    queryKey: ['report-orders', userId], queryFn: reportPayments.orders, enabled: Boolean(userId && service.data), retry: false,
  })
  const orderKey = ['report-order', userId, orderId]
  const selected = useQuery({
    queryKey: orderKey,
    queryFn: () => reportPayments.order(orderId),
    enabled: Boolean(userId && orderId),
    retry: false,
    refetchInterval: (query) => query.state.data?.status === 'pending' ? 5000 : false,
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
  const quote = useMutation({
    mutationFn: () => reportPayments.quote(category, Math.round(Number(budget) * 100), channel),
    onSuccess: (data) => { saveOrder(data); chooseOrder(data.order_id) },
  })
  const payment = useMutation({
    mutationFn: ({ operation, id }: { operation: 'confirm' | 'demoPay' | 'refresh'; id: string }) => reportPayments[operation](id),
    onSuccess: (data) => {
      if (useAuthStore.getState().userId !== userId) return
      saveOrder(data)
      if (data.checkout_url) window.location.assign(data.checkout_url)
    },
  })
  const { mutate: runPayment } = payment
  const canRefresh = Boolean(order && service.data?.enabled && order.mode !== 'demo'
    && order.mode === service.data.mode && (order.status === 'pending' || order.status === 'closed'))
  useEffect(() => {
    if (returnedFromAlipay && canRefresh && refreshedOnReturn.current !== orderId) {
      refreshedOnReturn.current = orderId
      runPayment({ operation: 'refresh', id: orderId })
    }
  }, [canRefresh, orderId, returnedFromAlipay, runPayment])
  const formError = quote.error ?? categories.error
  const paymentError = (payment.variables?.id === orderId ? payment.error : null) ?? selected.error
  const expired = order?.expired === true
  const currentMode = service.data?.mode
  const canPay = Boolean(service.data?.enabled && order && order.mode === currentMode && !expired)
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    quote.mutate()
  }

  return (
    <div className="aurora-bg h-full overflow-y-auto px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-6xl">
        <header className="mb-7 flex items-start gap-4">
          <span className="glass grid size-12 shrink-0 place-items-center text-brand-600"><FileText size={23} /></span>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-ink">欧米选购报告</h1>
            <p className="mt-2 text-sm text-ink-muted">{service.data?.description ?? '按品类和预算核对商品资料。'}</p>
          </div>
        </header>

        {currentMode && currentMode in modeLabels && (
          <p className="mb-4 flex items-center gap-2 text-sm font-medium text-ink-soft">
            <ShieldCheck size={17} /> {modeLabels[currentMode as keyof typeof modeLabels]}
          </p>
        )}
        {service.isError && <p role="alert" className="mb-4 text-sm text-ink">暂时无法读取支付服务。</p>}
        {service.data && !service.data.enabled && <p className="mb-4 text-sm text-ink-muted">报告收款暂未开通，已购报告仍可查看。</p>}
        {!userId && service.data?.enabled && (
          <Link to="/login" state={{ from: location.pathname + location.search }} className="btn-primary inline-flex">登录后获取报价</Link>
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
                  <button type="submit" className="btn-primary justify-self-start" disabled={quote.isPending || !category}>
                    {quote.isPending ? '正在报价…' : `获取报价 · 报告服务费 ${money(service.data.amount_fen)}`}
                  </button>
                  {formError && <p role="alert" className="text-sm text-ink">{formError.message}</p>}
                </form>
              </section>
            )}
            <section className="glass p-5 sm:p-6" aria-label="报告订单">
              <h2 className="text-lg font-semibold text-ink">报告订单</h2>
              {selected.isLoading && <p role="status" className="mt-3 text-sm text-ink-muted">正在查询订单…</p>}
              {order && (
                <div className="mt-3 space-y-3">
                  <p className="font-medium text-ink">{order.category} · {statusLabels[order.status]}</p>
                  <p className="text-sm text-ink-muted">
                    商品预算 {money(order.budget_fen)} · 共 {order.candidate_count} 款候选{order.channel === 'agent' ? ' · Agent 发起' : ''}
                  </p>
                  <p className="text-xl font-bold text-price">{money(order.amount_fen)}</p>
                  {order.mode in modeLabels && <p className="text-sm text-ink-muted">{modeLabels[order.mode as keyof typeof modeLabels]}</p>}
                  {order.status === 'paid' && <p className="break-all text-sm text-ink-muted">交易号 {order.trade_no}</p>}
                  {expired && order.status !== 'paid' && <p className="text-sm text-ink-muted">报价已过期。已付款时请先查询结果。</p>}
                  <div className="flex flex-wrap gap-2">
                    {canPay && (order.status === 'quoted' || (order.status === 'pending' && order.mode !== 'demo')) && (
                      <button className="btn-primary" disabled={payment.isPending} onClick={() => payment.mutate({ operation: 'confirm', id: orderId })}>
                        {order.mode === 'demo' ? '确认演示订单' : '确认订单并前往支付宝'}
                      </button>
                    )}
                    {canPay && order.status === 'pending' && order.mode === 'demo' && (
                      <button className="btn-primary" disabled={payment.isPending} onClick={() => payment.mutate({ operation: 'demoPay', id: orderId })}>
                        模拟付款成功
                      </button>
                    )}
                    {canRefresh && (
                      <button className="btn-secondary" disabled={payment.isPending} onClick={() => payment.mutate({ operation: 'refresh', id: orderId })}>
                        查询支付宝付款结果
                      </button>
                    )}
                  </div>
                </div>
              )}
              {paymentError && <p role="alert" className="mt-3 text-sm text-ink">{paymentError.message}</p>}
              {history.isError && <p role="alert" className="mt-3 text-sm text-ink">暂时无法读取历史订单。</p>}
              {!orderId && !history.data?.length && !history.isPending && <p className="mt-3 text-sm text-ink-muted">暂无报告订单。</p>}
              {Boolean(history.data?.length) && (
                <ul className="mt-4 space-y-2 border-t border-[var(--line)] pt-3">
                  {history.data?.map((item) => (
                    <li key={item.order_id}>
                      <button className="focus-ring flex w-full justify-between gap-3 rounded-md px-2 py-1 text-left text-sm text-ink-soft hover:bg-brand-500/10" aria-current={item.order_id === orderId ? 'true' : undefined} onClick={() => chooseOrder(item.order_id)}>
                        <span>{item.category} · {statusLabels[order?.order_id === item.order_id ? order.status : item.status]}</span>
                        <span>{money(item.amount_fen)}</span>
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
