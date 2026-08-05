import { useMemo, useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Armchair,
  Baby,
  ChevronLeft,
  ChevronRight,
  Droplets,
  Dumbbell,
  Laptop,
  LayoutGrid,
  RotateCcw,
  Search,
  Shirt,
  SlidersHorizontal,
  Soup,
  WandSparkles,
  X,
  type LucideIcon,
} from 'lucide-react'
import { api } from '@/api/client'
import { ProductCard, ProductCardSkeleton } from '@/components/product/ProductCard'
import { EmptyState } from '@/components/ui/EmptyState'
import { useCartStore } from '@/store/cartStore'
import { useChatStore } from '@/store/chatStore'
import { toast } from '@/store/toastStore'
import { cn } from '@/lib/utils'

const CATEGORIES: Array<{ label: string; icon: LucideIcon }> = [
  { label: '全部', icon: LayoutGrid },
  { label: '数码电子', icon: Laptop },
  { label: '美妆护肤', icon: WandSparkles },
  { label: '服饰运动', icon: Shirt },
  { label: '食品饮料', icon: Soup },
  { label: '家居用品', icon: Armchair },
  { label: '母婴用品', icon: Baby },
  { label: '运动户外', icon: Dumbbell },
  { label: '个护清洁', icon: Droplets },
]
const PAGE_SIZE = 24

export function ShopPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const category = searchParams.get('category') || '全部'
  const keyword = searchParams.get('q') || ''
  const page = Math.max(1, Number(searchParams.get('page') || 1))
  const [searchInput, setSearchInput] = useState(keyword)
  const addToCart = useCartStore((state) => state.addToCart)
  const askAgent = useChatStore((state) => state.askAgent)

  const query = useQuery({
    queryKey: ['products', { category, keyword, page }],
    queryFn: ({ signal }) => api.getProducts({
      category: category === '全部' ? undefined : category,
      keyword: keyword || undefined,
      page,
      page_size: PAGE_SIZE,
    }, signal),
    placeholderData: keepPreviousData,
  })
  const items = useMemo(() => query.data?.items ?? [], [query.data?.items])
  const total = query.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const updateParams = (updates: Record<string, string | number | null>) => {
    const next = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === '' || value === '全部' || (key === 'page' && value === 1)) next.delete(key)
      else next.set(key, String(value))
    })
    setSearchParams(next)
  }
  const submitSearch = (event?: FormEvent) => {
    event?.preventDefault()
    updateParams({ q: searchInput.trim(), page: null })
  }
  const featureIdx = useMemo(() => {
    const result = new Set<number>()
    for (let group = 0; group < items.length; group += 8) {
      const chunk = items.slice(group, group + 8)
      if (chunk.length < 4) break
      let best = 0
      chunk.forEach((product, index) => {
        if ((product.avg_rating ?? 0) > (chunk[best].avg_rating ?? 0)) best = index
      })
      result.add(group + best)
    }
    return result
  }, [items])

  return (
    <div className="aurora-bg flex h-full flex-col">
      <div className="glass-strong sticky top-0 z-10 border-b border-[var(--line)]">
        <div className="mx-auto max-w-6xl px-4 py-3">
          <form className="flex items-center gap-2" role="search" onSubmit={submitSearch}>
            <label className="flex flex-1 items-center gap-2 rounded-xl bg-[var(--field-bg)] px-3 py-2 focus-within:bg-[var(--glass-bg-strong)] focus-within:shadow-glow">
              <Search size={18} className="text-ink-muted" aria-hidden />
              <span className="sr-only">搜索商品或品牌</span>
              <input name="q" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="搜索商品、品牌…" className="w-full bg-transparent text-sm outline-none placeholder:text-ink-muted" />
              {searchInput && <button type="button" aria-label="清除搜索" onClick={() => { setSearchInput(''); updateParams({ q: null, page: null }) }} className="focus-ring rounded"><X size={16} className="text-ink-muted" /></button>}
            </label>
            <button className="btn-primary px-4 py-2 text-sm" type="submit">搜索</button>
          </form>
          <div className="mt-3 flex min-w-0 items-center gap-3">
            <div className="hidden shrink-0 items-center gap-2 text-xs font-semibold tracking-wide text-ink-muted md:flex">
              <span className="h-4 w-0.5 rounded-full bg-brand-500" />
              分类
            </div>
            <div className="no-scrollbar min-w-0 flex-1 overflow-x-auto" aria-label="商品分类">
              <div className="flex w-max min-w-full items-center gap-1 rounded-2xl border border-[var(--line)] bg-[var(--field-bg)] p-1">
                {CATEGORIES.map(({ label, icon: Icon }) => {
                  const active = category === label
                  return (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={active}
                      onClick={() => updateParams({ category: label, page: null })}
                      className={cn(
                        'focus-ring group flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
                        active
                          ? 'bg-[var(--surface)] text-ink shadow-sm ring-1 ring-brand-500/15'
                          : 'text-ink-muted hover:bg-[var(--surface-variant)] hover:text-ink',
                      )}
                    >
                      <Icon
                        size={15}
                        strokeWidth={active ? 2.25 : 1.8}
                        className={cn('transition-colors', active ? 'text-brand-500' : 'text-ink-muted group-hover:text-brand-500')}
                        aria-hidden
                      />
                      {label}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-4 py-4">
          {query.isPending ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{Array.from({ length: 10 }, (_, index) => <ProductCardSkeleton key={index} />)}</div>
          ) : query.isError ? (
            <EmptyState icon={<RotateCcw size={26} />} title="商品加载失败" description={query.error instanceof Error ? query.error.message : '请检查网络后重试'} action={<button className="btn-primary" onClick={() => void query.refetch()}>重新加载</button>} />
          ) : items.length === 0 ? (
            <EmptyState icon={<SlidersHorizontal size={26} />} title="没有找到相关商品" description="换个关键词或分类试试吧" />
          ) : (
            <>
              <div className="mb-4 flex items-end justify-between gap-4 border-b border-[var(--line)] pb-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-500">Curated products</p>
                  <h1 className="mt-1 text-xl font-bold tracking-tight text-ink">{category === '全部' ? '全部好物' : category}</h1>
                  {keyword && <p className="mt-1 text-xs text-ink-muted">搜索“{keyword}”的相关结果</p>}
                </div>
                <div className="pb-0.5 text-right">
                  <p className="text-sm font-medium tabular-nums text-ink-soft">{total.toLocaleString()} 件</p>
                  {query.isFetching && <span className="text-xs text-brand-600" role="status">正在更新…</span>}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                {items.map((product, index) => <ProductCard key={product.product_id} product={product} variant={featureIdx.has(index) ? 'feature' : 'grid'} className={featureIdx.has(index) ? 'lg:col-span-2 lg:row-span-2' : undefined} spotlightHover onClick={() => navigate(`/product/${product.product_id}`)} onAddToCart={async () => { const ok = await addToCart(product.product_id); if (ok) toast.success('已加入购物车') }} onAskAgent={() => { void askAgent(product.product_id, product.title); navigate('/chat') }} />)}
              </div>
              <nav className="mt-6 flex items-center justify-center gap-3 pb-6" aria-label="商品分页">
                <button className="btn-secondary inline-flex items-center gap-1" disabled={page <= 1} onClick={() => updateParams({ page: page - 1 })}><ChevronLeft size={16} />上一页</button>
                <span className="min-w-20 text-center text-sm text-ink-muted">{page} / {pageCount}</span>
                <button className="btn-secondary inline-flex items-center gap-1" disabled={page >= pageCount} onClick={() => updateParams({ page: page + 1 })}>下一页<ChevronRight size={16} /></button>
              </nav>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
