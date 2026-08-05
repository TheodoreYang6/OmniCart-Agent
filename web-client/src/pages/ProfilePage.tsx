import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowUpRight,
  Heart,
  Info,
  LockKeyhole,
  LogIn,
  LogOut,
  MapPin,
  Receipt,
  ShieldCheck,
  ShoppingBag,
  ShoppingCart,
  Sparkles,
  UserCircle2,
} from 'lucide-react'
import { api } from '@/api/client'
import type { PreferenceEntry } from '@/api/types'
import { OmiAppIcon } from '@/components/brand/OmiAppIcon'
import { Spinner } from '@/components/ui/Spinner'
import { AGENT_NAME, APP_NAME } from '@/config'
import { useAuthStore } from '@/store/authStore'
import { useCartStore } from '@/store/cartStore'
import { toast } from '@/store/toastStore'

interface ProfileDashboardData {
  cartCount: number
  orderCount: number | null
  addressCount: number | null
  preferenceCount: number | null
  preferences: PreferenceEntry[]
  isLoading: boolean
  hasError: boolean
}

export function ProfilePage() {
  const navigate = useNavigate()
  const isLoggedIn = useAuthStore((state) => state.isLoggedIn())
  const userId = useAuthStore((state) => state.userId)
  const username = useAuthStore((state) => state.username)
  const email = useAuthStore((state) => state.email)
  const logout = useAuthStore((state) => state.logout)
  const cartItems = useCartStore((state) => state.items)
  const cartLoaded = useCartStore((state) => state.hasLoaded)
  const loadCart = useCartStore((state) => state.loadCart)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  useEffect(() => {
    if (!cartLoaded) void loadCart()
  }, [cartLoaded, loadCart])

  const orders = useQuery({
    queryKey: ['profile-dashboard', 'orders', userId],
    queryFn: () => api.getOrders(userId),
    enabled: isLoggedIn && Boolean(userId),
    staleTime: 30_000,
  })
  const addresses = useQuery({
    queryKey: ['profile-dashboard', 'addresses', userId],
    queryFn: () => api.getAddresses(userId),
    enabled: isLoggedIn && Boolean(userId),
    staleTime: 30_000,
  })
  const preferences = useQuery({
    queryKey: ['profile-dashboard', 'preferences', userId],
    queryFn: () => api.getPreferenceEntries(userId),
    enabled: isLoggedIn && Boolean(userId),
    staleTime: 30_000,
  })

  const dashboard = useMemo<ProfileDashboardData>(() => ({
    cartCount: cartItems.reduce((sum, item) => sum + item.quantity, 0),
    orderCount: isLoggedIn ? (orders.data?.count ?? 0) : null,
    addressCount: isLoggedIn ? (addresses.data?.addresses.length ?? 0) : null,
    preferenceCount: isLoggedIn ? (preferences.data?.count ?? 0) : null,
    preferences: preferences.data?.entries.filter((entry) => entry.enabled).slice(0, 3) ?? [],
    isLoading: isLoggedIn && (orders.isLoading || addresses.isLoading || preferences.isLoading),
    hasError: isLoggedIn && (orders.isError || addresses.isError || preferences.isError),
  }), [addresses, cartItems, isLoggedIn, orders, preferences])

  const handleLogout = async () => {
    setIsLoggingOut(true)
    const ok = await logout()
    setIsLoggingOut(false)
    if (ok) {
      toast.success('已安全退出，已切换为游客身份')
      navigate('/chat', { replace: true })
    } else {
      toast.error('退出失败，当前登录状态已保留，请重试')
    }
  }

  const entries = [
    { icon: Receipt, title: '我的订单', description: '追踪订单与历史购买', value: dashboard.orderCount, to: '/orders' },
    { icon: MapPin, title: '收货地址', description: '管理常用配送信息', value: dashboard.addressCount, to: '/address' },
    { icon: Heart, title: '偏好设置', description: `管理${AGENT_NAME}的长期记忆`, value: dashboard.preferenceCount, to: '/preferences' },
  ]

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-[radial-gradient(circle_at_72%_8%,rgba(78,112,255,0.10),transparent_34%)]">
      <div className="mx-auto w-full max-w-[1180px] px-4 py-5 sm:px-6 sm:py-8 xl:px-8">
        <header className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand-500">Personal workspace</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">我的工作台</h1>
            <p className="mt-1 text-sm text-ink-muted">你的订单、地址与购物偏好，都在这里。</p>
          </div>
          {dashboard.isLoading && <Spinner size={20} className="text-brand-500" />}
        </header>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12 lg:gap-5">
          <section className="profile-spotlight relative overflow-hidden rounded-[28px] border border-white/10 bg-brand-gradient p-6 text-white shadow-float sm:p-8 lg:col-span-7">
            <div className="pointer-events-none absolute -right-16 -top-20 h-64 w-64 rounded-full bg-white/15 blur-3xl" />
            <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center">
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-[24px] border border-white/20 bg-white/15 text-3xl font-bold shadow-inner backdrop-blur-sm">
                {isLoggedIn ? (username[0]?.toUpperCase() ?? 'U') : <UserCircle2 size={38} />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="truncate text-2xl font-bold sm:text-3xl">{isLoggedIn ? username : '你好，未来会员'}</h2>
                  <span className="inline-flex items-center gap-1 rounded-full bg-white/15 px-2.5 py-1 text-xs text-white/85">
                    {isLoggedIn ? <ShieldCheck size={13} /> : <LockKeyhole size={13} />}
                    {isLoggedIn ? '账号已同步' : '游客模式'}
                  </span>
                </div>
                <p className="mt-2 truncate text-sm text-white/72">
                  {isLoggedIn ? email || '欢迎回来，今天也一起挑到更合适的商品。' : '登录后同步购物车、订单、地址和欧米记忆。'}
                </p>
                <div className="mt-5 flex flex-wrap gap-2.5">
                  {isLoggedIn ? (
                    <button type="button" onClick={() => navigate('/chat')} className="focus-ring inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-brand-700 shadow-sm transition hover:-translate-y-0.5">
                      <Sparkles size={16} /> 和{AGENT_NAME}继续聊
                    </button>
                  ) : (
                    <button type="button" onClick={() => navigate('/login', { state: { from: '/profile' } })} className="focus-ring inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-brand-700 shadow-sm transition hover:-translate-y-0.5">
                      <LogIn size={16} /> 登录并开启完整体验
                    </button>
                  )}
                  <button type="button" onClick={() => navigate('/shop')} className="focus-ring inline-flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-white/15">
                    <ShoppingBag size={16} /> 去逛商品
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section className="relative overflow-hidden rounded-[28px] border border-[var(--line)] bg-[var(--surface)] p-5 shadow-soft sm:p-6 lg:col-span-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-500">Omi memory</p>
                <h2 className="mt-1 text-lg font-bold text-ink">{AGENT_NAME}记住的你</h2>
              </div>
              <OmiAppIcon size={48} decorative />
            </div>
            {isLoggedIn ? (
              dashboard.preferences.length > 0 ? (
                <div className="mt-5 space-y-2.5">
                  {dashboard.preferences.map((entry) => (
                    <div key={entry.entry_id} className="rounded-2xl border border-[var(--line)] bg-[var(--surface-variant)] px-4 py-3">
                      <p className="line-clamp-1 text-sm font-medium text-ink">{entry.raw_text}</p>
                      <p className="mt-1 text-xs text-ink-muted">{[entry.category, entry.sub_category].filter(Boolean).join(' · ') || '通用偏好'}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-5 rounded-2xl border border-dashed border-[var(--line)] p-5 text-sm leading-relaxed text-ink-muted">还没有长期偏好。和{AGENT_NAME}聊聊预算、品牌或使用场景，它会逐渐更懂你。</div>
              )
            ) : (
              <div className="mt-5 rounded-2xl border border-dashed border-[var(--line)] p-5">
                <div className="flex items-center gap-2 text-sm font-medium text-ink"><LockKeyhole size={16} className="text-brand-500" /> 登录后解锁长期记忆</div>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">欧米可以记住你的预算、肤质、品牌和避雷项，让每次推荐更贴近你。</p>
              </div>
            )}
            <button type="button" onClick={() => isLoggedIn ? navigate('/preferences') : navigate('/login', { state: { from: '/preferences' } })} className="focus-ring mt-4 inline-flex items-center gap-1.5 rounded-lg text-sm font-semibold text-brand-600 hover:text-brand-700">
              管理欧米记忆 <ArrowUpRight size={15} />
            </button>
          </section>

          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:col-span-12">
            <MetricCard icon={ShoppingCart} label="购物车商品" value={dashboard.cartCount} onClick={() => navigate('/cart')} />
            <MetricCard icon={Receipt} label="历史订单" value={dashboard.orderCount} locked={!isLoggedIn} onClick={() => navigateProtected('/orders', isLoggedIn, navigate)} />
            <MetricCard icon={MapPin} label="收货地址" value={dashboard.addressCount} locked={!isLoggedIn} onClick={() => navigateProtected('/address', isLoggedIn, navigate)} />
            <MetricCard icon={Heart} label="偏好记忆" value={dashboard.preferenceCount} locked={!isLoggedIn} onClick={() => navigateProtected('/preferences', isLoggedIn, navigate)} />
          </section>

          <section className="grid gap-3 md:grid-cols-3 lg:col-span-12">
            {entries.map(({ icon: Icon, title, description, value, to }) => (
              <button key={to} type="button" onClick={() => navigateProtected(to, isLoggedIn, navigate)} className="group focus-ring flex min-h-36 items-start gap-4 rounded-[24px] border border-[var(--line)] bg-[var(--surface)] p-5 text-left shadow-soft transition hover:-translate-y-1 hover:border-brand-400/45 hover:shadow-float">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-500"><Icon size={22} /></span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center justify-between gap-3 text-base font-semibold text-ink">{title}<ArrowUpRight size={17} className="text-ink-muted transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-brand-500" /></span>
                  <span className="mt-1 block text-sm text-ink-muted">{description}</span>
                  <span className="mt-4 block text-xs font-medium text-brand-500">{isLoggedIn ? `${value ?? 0} 项数据` : '登录后查看'}</span>
                </span>
              </button>
            ))}
          </section>

          <section className="flex flex-col justify-between gap-4 rounded-[24px] border border-[var(--line)] bg-[var(--surface)] p-5 sm:flex-row sm:items-center lg:col-span-12">
            <div className="flex items-center gap-3">
              <OmiAppIcon size={44} decorative />
              <div>
                <p className="font-semibold text-ink">{APP_NAME} · {AGENT_NAME}购物智能体</p>
                <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted"><Info size={13} /> 文字、语音、图片与可解释商品决策</p>
              </div>
            </div>
            {isLoggedIn && (
              <button type="button" disabled={isLoggingOut} onClick={handleLogout} className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl border border-rose-500/20 px-4 py-2.5 text-sm font-medium text-rose-500 transition hover:bg-rose-500/8 disabled:opacity-60">
                {isLoggingOut ? <Spinner size={16} /> : <LogOut size={16} />} 退出登录
              </button>
            )}
          </section>
        </div>

        {dashboard.hasError && <p role="status" className="mt-4 rounded-xl bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">部分摘要暂时加载失败，入口仍可正常使用。</p>}
      </div>
    </div>
  )
}

function MetricCard({ icon: Icon, label, value, locked = false, onClick }: { icon: typeof ShoppingCart; label: string; value: number | null; locked?: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="group focus-ring rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-left shadow-soft transition hover:border-brand-400/40 sm:p-5">
      <span className="flex items-center justify-between text-ink-muted"><Icon size={18} />{locked && <LockKeyhole size={14} />}</span>
      <strong className="mt-4 block text-2xl font-bold tabular-nums text-ink">{locked ? '—' : value ?? 0}</strong>
      <span className="mt-1 block text-xs text-ink-muted">{label}</span>
    </button>
  )
}

function navigateProtected(path: string, loggedIn: boolean, navigate: ReturnType<typeof useNavigate>) {
  if (loggedIn) navigate(path)
  else navigate('/login', { state: { from: path } })
}
