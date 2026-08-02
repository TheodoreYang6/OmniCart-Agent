import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, SlidersHorizontal, X } from 'lucide-react'
import { api } from '@/api/client'
import type { Product } from '@/api/types'
import { ProductCard, ProductCardSkeleton } from '@/components/product/ProductCard'
import { EmptyState } from '@/components/ui/EmptyState'
import { Spinner } from '@/components/ui/Spinner'
import { useCartStore } from '@/store/cartStore'
import { useChatStore } from '@/store/chatStore'
import { toast } from '@/store/toastStore'
import { categoryIcon } from '@/lib/format'
import { cn } from '@/lib/utils'

const CATEGORIES = ['全部', '数码电子', '美妆护肤', '服饰运动', '食品饮料', '家居用品', '母婴用品', '运动户外', '个护清洁']
const PAGE_SIZE = 24

export function ShopPage() {
  const navigate = useNavigate()
  const addToCart = useCartStore((s) => s.addToCart)
  const askAgent = useChatStore((s) => s.askAgent)

  const [category, setCategory] = useState('全部')
  const [keyword, setKeyword] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [items, setItems] = useState<Product[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const sentinelRef = useRef<HTMLDivElement>(null)

  const fetchPage = useCallback(
    async (opts: { category: string; keyword: string; page: number; append: boolean }) => {
      if (opts.append) setLoadingMore(true)
      else setLoading(true)
      try {
        const res = await api.getProducts({
          category: opts.category === '全部' ? undefined : opts.category,
          keyword: opts.keyword || undefined,
          page: opts.page,
          page_size: PAGE_SIZE,
        })
        setTotal(res.total)
        setItems((prev) => (opts.append ? [...prev, ...res.items] : res.items))
      } catch {
        toast.error('加载商品失败，请稍后重试')
        if (!opts.append) setItems([])
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [],
  )

  useEffect(() => {
    setPage(1)
    fetchPage({ category, keyword, page: 1, append: false })
  }, [category, keyword, fetchPage])

  const hasMore = items.length < total

  // 无限滚动
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || !hasMore || loading) return
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore) {
          const next = page + 1
          setPage(next)
          fetchPage({ category, keyword, page: next, append: true })
        }
      },
      { rootMargin: '400px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [hasMore, loading, loadingMore, page, category, keyword, fetchPage])

  const submitSearch = () => setKeyword(searchInput.trim())

  const handleAsk = (productId: string, title: string) => {
    askAgent(productId, title)
    navigate('/chat')
  }

  // Bento 大卡选拔（P4）：每 8 张一组取评分最高的一张；尾组不足 4 张不放大（避免孤大卡撙行）
  const featureIdx = useMemo(() => {
    const set = new Set<number>()
    for (let g = 0; g < items.length; g += 8) {
      const chunk = items.slice(g, g + 8)
      if (chunk.length < 4) break
      let best = 0
      chunk.forEach((p, i) => {
        if ((p.avg_rating ?? 0) > (chunk[best].avg_rating ?? 0)) best = i
      })
      set.add(g + best)
    }
    return set
  }, [items])

  const grid = useMemo(
    () => (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {items.map((p, i) => {
          // Bento 混排（P4）：每 8 张一组，组内评分最高的在 lg 占 2x2；尾组不足 4 张不放大
          const isFeature = featureIdx.has(i)
          return (
            <ProductCard
              key={p.product_id}
              product={p}
              variant={isFeature ? 'feature' : 'grid'}
              className={isFeature ? 'lg:col-span-2 lg:row-span-2' : undefined}
              spotlightHover
              onClick={() => navigate(`/product/${p.product_id}`)}
              onAddToCart={async () => {
                const ok = await addToCart(p.product_id)
                if (ok) toast.success('已加入购物车')
              }}
              onAskAgent={() => handleAsk(p.product_id, p.title)}
            />
          )
        })}
      </div>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, featureIdx],
  )

  return (
    <div className="aurora-bg flex h-full flex-col">
      {/* 搜索 + 分类：玻璃吸顶条 */}
      <div className="glass-strong sticky top-0 z-10 border-b border-[var(--line)]">
        <div className="mx-auto max-w-6xl px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex flex-1 items-center gap-2 rounded-xl bg-[var(--field-bg)] px-3 py-2 transition focus-within:bg-[var(--glass-bg-strong)] focus-within:shadow-glow">
              <Search size={18} className="text-ink-muted" />
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submitSearch()}
                placeholder="搜索商品、品牌…"
                className="w-full bg-transparent text-sm outline-none placeholder:text-ink-muted"
              />
              {searchInput && (
                <button
                  onClick={() => {
                    setSearchInput('')
                    setKeyword('')
                  }}
                >
                  <X size={16} className="text-ink-muted" />
                </button>
              )}
            </div>
            <button onClick={submitSearch} className="btn-primary px-4 py-2 text-sm">
              搜索
            </button>
          </div>

          <div className="no-scrollbar mt-3 flex gap-2 overflow-x-auto pb-0.5">
            {CATEGORIES.map((c) => (
              <button
                key={c}
                onClick={() => setCategory(c)}
                className={cn(
                  'flex shrink-0 items-center gap-1 rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-200',
                  category === c
                    ? 'gradient-brand border border-transparent text-white shadow-glow'
                    : 'border border-[var(--field-border)] bg-[var(--field-bg)] text-ink-soft backdrop-blur hover:border-brand-300 hover:text-brand-600',
                )}
              >
                {c !== '全部' && <span>{categoryIcon(c)}</span>}
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 商品网格 */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-4 py-4">
          {loading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {Array.from({ length: 10 }).map((_, i) => (
                <ProductCardSkeleton key={i} />
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={<SlidersHorizontal size={26} />}
              title="没有找到相关商品"
              description="换个关键词或分类试试吧"
            />
          ) : (
            <>
              <p className="mb-3 text-sm text-ink-muted">
                共 {total} 件商品{keyword && ` · “${keyword}”`}
              </p>
              {grid}
              <div ref={sentinelRef} className="flex justify-center py-6">
                {loadingMore && <Spinner size={24} />}
                {!hasMore && items.length > 0 && (
                  <span className="text-xs text-ink-muted">— 已经到底啦 —</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
