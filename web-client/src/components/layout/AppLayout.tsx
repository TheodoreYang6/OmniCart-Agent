import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  MessageCircleHeart,
  Store,
  ShoppingCart,
  User,
} from 'lucide-react'
import { OmiAppIcon } from '@/components/brand/OmiAppIcon'
import { ThemeToggle } from '@/components/ui/ThemeToggle'
import { useAuthStore } from '@/store/authStore'
import { useCartStore } from '@/store/cartStore'
import { useChatStore } from '@/store/chatStore'
import { cn } from '@/lib/utils'
import { AGENT_NAME, APP_NAME } from '@/config'

interface NavItem {
  to: string
  label: string
  icon: typeof Store
}

const NAV: NavItem[] = [
  { to: '/chat', label: `${AGENT_NAME}对话`, icon: MessageCircleHeart },
  { to: '/shop', label: '商品', icon: Store },
  { to: '/cart', label: '购物车', icon: ShoppingCart },
  { to: '/profile', label: '我的', icon: User },
]

/**
 * 响应式应用外壳。
 * - 桌面(lg+)：左侧固定侧边栏 + 右侧内容
 * - 移动端：顶部品牌栏 + 底部 Tab 导航
 * 聊天页需要满高布局，因此内容区使用 flex + min-h-0，由各页自行滚动。
 */
export function AppLayout() {
  const location = useLocation()
  const username = useAuthStore((s) => s.username)
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())
  const initialized = useAuthStore((s) => s.initialized)
  const cartCount = useCartStore((s) => s.items.reduce((sum, i) => sum + i.quantity, 0))
  const loadCart = useCartStore((s) => s.loadCart)
  const setContext = useCartStore((s) => s.setContext)
  const sessionId = useChatStore((s) => s.sessionId)

  useEffect(() => {
    setContext(sessionId, '')
  }, [sessionId, setContext])

  useEffect(() => {
    // 购物车是登录用户数据。游客不预拉取，避免每次进入页面都产生 401，
    // 再被身份恢复逻辑误判成 token 失效。
    if (initialized && isLoggedIn) void loadCart()
  }, [initialized, isLoggedIn, loadCart])

  const isChat = location.pathname.startsWith('/chat')
  const rootTabs = ['/chat', '/shop', '/cart', '/profile']
  const isRootTab = rootTabs.includes(location.pathname)

  return (
    <div className="flex h-[100dvh] w-full overflow-hidden">
      {/* 桌面侧边栏：玻璃条 */}
      <aside className="glass-strong z-10 hidden w-64 shrink-0 flex-col border-r border-[var(--line)] lg:flex">
        {/* 品牌区：ThemeToggle 已下移至底部，释出约 66px 给文案，
            副标语不再被 truncate 切成「购物智...」 */}
        <div className="flex items-center gap-3 px-5 py-5">
          <OmiAppIcon size={44} />
          <div className="min-w-0">
            <p className="gradient-text text-[17px] font-extrabold leading-none">{APP_NAME}</p>
            <p className="mt-1.5 whitespace-nowrap text-xs text-ink-muted">
              {AGENT_NAME} · 购物智能体
            </p>
          </div>
        </div>

        <nav className="flex-1 space-y-1.5 px-3 py-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'group relative flex items-center gap-3 overflow-hidden rounded-xl px-3.5 py-3 text-[15px] font-medium transition-all duration-200',
                  isActive
                    ? 'gradient-brand text-white shadow-glow'
                    : 'text-ink-soft hover:bg-[var(--glass-bg-strong)] hover:text-brand-600',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {/* 激活态左侧高亮竖条：当前位置更明确 */}
                  {isActive && (
                    <span className="absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-r-full bg-white/90" />
                  )}
                  <span
                    className={cn(
                      'relative transition-transform duration-200 group-hover:scale-110',
                      isActive && 'scale-110',
                    )}
                  >
                    <item.icon size={20} />
                    {item.to === '/cart' && cartCount > 0 && (
                      <span className="absolute -right-2 -top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-price px-1 text-[10px] font-bold text-white">
                        {cartCount > 99 ? '99+' : cartCount}
                      </span>
                    )}
                  </span>
                  <span className="whitespace-nowrap">{item.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 底部：用户卡 + 主题开关同区 */}
        <div className="m-3 space-y-2">
          <NavLink to="/profile" className="glass card-hover flex items-center gap-3 p-3">
            <div className="gradient-brand flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white shadow-glow">
              {isLoggedIn ? (username[0]?.toUpperCase() ?? 'U') : '游'}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink">
                {isLoggedIn ? username : '未登录'}
              </p>
              <p className="truncate text-xs text-ink-muted">
                {isLoggedIn ? '查看个人中心' : '点击登录 / 注册'}
              </p>
            </div>
          </NavLink>
          <div className="flex items-center justify-between rounded-xl px-1">
            <span className="text-xs text-ink-muted">外观主题</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* 主内容区 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 移动端顶部栏（聊天页有自己的头部，避免重复） */}
        {!isChat && isRootTab && (
          <header className="glass-strong z-10 flex items-center gap-2 border-b border-[var(--line)] px-4 py-3 lg:hidden">
            <OmiAppIcon size={36} />
            <span className="gradient-text font-extrabold">{APP_NAME}</span>
            <ThemeToggle className="ml-auto" />
          </header>
        )}

        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <Outlet />
        </main>

        {/* 移动端底部 Tab：玻璃悬浮条 */}
        {isRootTab && <nav className="glass-strong z-10 flex shrink-0 items-stretch border-t border-[var(--line)] pb-[env(safe-area-inset-bottom)] lg:hidden" aria-label="主要导航">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-all duration-200',
                  isActive ? 'text-brand-600' : 'text-ink-muted',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      'relative rounded-xl px-3 py-0.5 transition-all duration-200',
                      isActive && '-translate-y-0.5 bg-brand-50 shadow-glow dark:bg-brand-500/15',
                    )}
                  >
                    <item.icon size={22} strokeWidth={isActive ? 2.4 : 2} />
                    {item.to === '/cart' && cartCount > 0 && (
                      <span className="absolute -right-1 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-price px-1 text-[9px] font-bold text-white">
                        {cartCount > 99 ? '99+' : cartCount}
                      </span>
                    )}
                  </span>
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>}
      </div>
    </div>
  )
}
