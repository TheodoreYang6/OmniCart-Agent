import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, Lock, User, Mail, Phone } from 'lucide-react'
import { Omi } from '@/components/brand/Omi'
import { useAuthStore } from '@/store/authStore'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/store/toastStore'
import { AGENT_NAME, APP_NAME } from '@/config'
import { cn } from '@/lib/utils'

export function LoginPage() {
  const navigate = useNavigate()
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const isLoading = useAuthStore((s) => s.isLoading)
  const error = useAuthStore((s) => s.error)
  const clearError = useAuthStore((s) => s.clearError)

  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [showPwd, setShowPwd] = useState(false)

  const submit = async () => {
    clearError()
    const ok = isRegister
      ? await register(username, password, email, phone)
      : await login(username, password)
    if (ok) {
      toast.success(isRegister ? '注册成功' : '登录成功')
      navigate('/chat', { replace: true })
    }
  }

  return (
    <div className="aurora-bg flex h-[100dvh] w-full">
      {/* 品牌展示区（桌面） */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-brand-gradient p-12 text-white lg:flex">
        <div className="absolute -right-20 -top-20 h-72 w-72 rounded-full bg-white/10 blur-2xl" />
        <div className="absolute -bottom-24 -left-10 h-80 w-80 rounded-full bg-white/10 blur-2xl" />
        <div className="relative flex items-center gap-2.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
            <Omi size={34} />
          </div>
          <span className="text-xl font-bold">{APP_NAME}</span>
        </div>
        <div className="relative">
          <Omi size={132} withBody float expression="wink" className="mb-4" />
          <h1 className="text-4xl font-bold leading-tight">
            嗨，我是{AGENT_NAME}
            <br />
            你的购物智能体
          </h1>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-white/80">
            多模态购物智能体 · 探索未来购物新范式。聊需求、传图片、说一句话，
            欧米就能结合真实评价与官方信息，帮你挑到对的那一件。
          </p>
        </div>
        <div className="relative flex gap-3 text-sm text-white/70">
          <span>多模态检索</span>·<span>决策可解释</span>·<span>长期偏好记忆</span>
        </div>
      </div>

      {/* 表单区 */}
      <div className="flex flex-1 flex-col">
        <div className="flex items-center gap-2 p-4 lg:hidden">
          <button
            onClick={() => navigate('/chat')}
            className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-soft transition hover:bg-[var(--surface-variant)]"
          >
            <ArrowLeft size={20} />
          </button>
        </div>

        <div className="flex flex-1 items-center justify-center px-6 pb-10">
          <div className="w-full max-w-sm">
            <div className="mb-8 lg:hidden">
              <Omi size={64} withBody expression="wink" />
            </div>
            <h2 className="text-2xl font-bold text-ink">
              {isRegister ? '创建账号' : '欢迎回来'}
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              {isRegister ? `注册后开启专属 ${AGENT_NAME} 购物体验` : '登录以同步你的购物车与偏好'}
            </p>

            <div className="mt-6 space-y-3">
              <Field icon={<User size={18} />} placeholder="用户名" value={username} onChange={setUsername} />
              <Field
                icon={<Lock size={18} />}
                placeholder="密码"
                value={password}
                onChange={setPassword}
                type={showPwd ? 'text' : 'password'}
                onSubmit={submit}
                trailing={
                  <button
                    onClick={() => setShowPwd((v) => !v)}
                    className="text-ink-muted transition hover:text-ink"
                    type="button"
                  >
                    {showPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                }
              />
              {isRegister && (
                <>
                  <Field
                    icon={<Mail size={18} />}
                    placeholder="邮箱（选填）"
                    value={email}
                    onChange={setEmail}
                  />
                  <Field
                    icon={<Phone size={18} />}
                    placeholder="手机号（选填）"
                    value={phone}
                    onChange={setPhone}
                  />
                </>
              )}
            </div>

            {error && <p className="mt-3 text-sm text-rose-500">{error}</p>}

            <button
              onClick={submit}
              disabled={isLoading}
              className="btn-primary mt-5 w-full py-3 text-base"
            >
              {isLoading ? <Spinner size={20} className="text-white" /> : isRegister ? '注册' : '登录'}
            </button>

            <p className="mt-4 text-center text-sm text-ink-muted">
              {isRegister ? '已有账号？' : '还没有账号？'}
              <button
                onClick={() => {
                  setIsRegister((v) => !v)
                  clearError()
                }}
                className="ml-1 font-medium text-brand-600 hover:underline"
              >
                {isRegister ? '去登录' : '免费注册'}
              </button>
            </p>

            <button
              onClick={() => navigate('/chat')}
              className="mt-6 w-full text-center text-sm text-ink-muted hover:text-ink"
            >
              先随便逛逛 →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

interface FieldProps {
  icon: React.ReactNode
  placeholder: string
  value: string
  onChange: (v: string) => void
  type?: string
  trailing?: React.ReactNode
  onSubmit?: () => void
}

function Field({ icon, placeholder, value, onChange, type = 'text', trailing, onSubmit }: FieldProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-2.5 rounded-xl border border-[var(--field-border)] bg-[var(--glass-bg-strong)] px-3.5 py-3 backdrop-blur transition',
        'focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-500/10',
      )}
    >
      <span className="text-ink-muted">{icon}</span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onSubmit?.()}
        className="w-full bg-transparent text-[15px] outline-none placeholder:text-ink-muted"
      />
      {trailing}
    </div>
  )
}
