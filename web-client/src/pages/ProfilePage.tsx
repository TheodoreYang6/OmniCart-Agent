import { useNavigate } from 'react-router-dom'
import {
  ChevronRight,
  Heart,
  LogOut,
  MapPin,
  Receipt,
  UserCircle2,
  LogIn,
  Info,
} from 'lucide-react'
import { Omi } from '@/components/brand/Omi'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toastStore'
import { AGENT_NAME, APP_NAME } from '@/config'

export function ProfilePage() {
  const navigate = useNavigate()
  const isLoggedIn = useAuthStore((s) => s.token.length > 0)
  const username = useAuthStore((s) => s.username)
  const email = useAuthStore((s) => s.email)
  const logout = useAuthStore((s) => s.logout)

  const menu = [
    { icon: Receipt, label: '我的订单', desc: '查看历史订单', to: '/orders' },
    { icon: MapPin, label: '收货地址', desc: '管理收货信息', to: '/address' },
    { icon: Heart, label: '偏好设置', desc: `让${AGENT_NAME}更懂你`, to: '/preferences' },
  ]

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-4 py-4">
        {/* 用户卡片 */}
        <div className="overflow-hidden rounded-2xl bg-brand-gradient p-5 text-white shadow-float">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white/20 text-2xl font-bold backdrop-blur">
              {isLoggedIn ? (username[0]?.toUpperCase() ?? 'U') : <UserCircle2 size={32} />}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xl font-bold">{isLoggedIn ? username : '游客用户'}</p>
              <p className="mt-0.5 truncate text-sm text-white/70">
                {isLoggedIn ? email || '欢迎回来 👋' : '登录后同步购物车、地址与偏好'}
              </p>
            </div>
            {!isLoggedIn && (
              <button
                onClick={() => navigate('/login')}
                className="flex items-center gap-1.5 rounded-xl bg-white/20 px-4 py-2 text-sm font-medium backdrop-blur transition hover:bg-[var(--field-bg)]"
              >
                <LogIn size={16} /> 登录
              </button>
            )}
          </div>
        </div>

        {/* 菜单 */}
        <div className="glass mt-4 overflow-hidden">
          {menu.map((m, i) => (
            <button
              key={m.to}
              onClick={() => navigate(m.to)}
              className={`flex w-full items-center gap-3.5 px-4 py-4 transition hover:bg-[var(--surface-variant)] ${
                i > 0 ? 'border-t border-[var(--line)]' : ''
              }`}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500 dark:text-brand-300">
                <m.icon size={20} />
              </div>
              <div className="flex-1 text-left">
                <p className="text-sm font-medium text-ink">{m.label}</p>
                <p className="text-xs text-ink-muted">{m.desc}</p>
              </div>
              <ChevronRight size={18} className="text-ink-muted" />
            </button>
          ))}
        </div>

        {/* 关于 */}
        <div className="glass mt-4 p-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 ring-1 ring-brand-500/15">
              <Omi size={34} />
            </div>
            <div>
              <p className="text-sm font-semibold text-ink">{APP_NAME} · {AGENT_NAME}购物智能体</p>
              <p className="text-xs text-ink-muted">多模态购物智能体 · 探索未来购物新范式</p>
            </div>
          </div>
          <div className="mt-3 flex items-start gap-2 rounded-xl bg-[var(--field-bg)] p-3 text-xs leading-relaxed text-ink-muted backdrop-blur">
            <Info size={14} className="mt-0.5 shrink-0 text-ink-muted" />
            <span>
              支持文字 / 语音 / 图片多模态交互，从挑选到下单全程可解释，与安卓端共享同一后端账户与数据。
            </span>
          </div>
        </div>

        {/* 退出登录 */}
        {isLoggedIn && (
          <button
            onClick={() => {
              logout()
              toast.success('已退出登录')
            }}
            className="glass card-hover mt-4 flex w-full items-center justify-center gap-2 py-3.5 text-sm font-medium text-rose-500 transition hover:bg-rose-500/10"
          >
            <LogOut size={18} /> 退出登录
          </button>
        )}
      </div>
    </div>
  )
}
