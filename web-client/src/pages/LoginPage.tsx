import { useState, type FormEvent, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, Lock, User, Mail, Phone } from 'lucide-react'
import { Omi } from '@/components/brand/Omi'
import { OmiHero } from '@/components/brand/OmiHero'
import { useAuthStore } from '@/store/authStore'
import { Spinner } from '@/components/ui/Spinner'
import { toast } from '@/store/toastStore'
import { AGENT_NAME, APP_NAME } from '@/config'
import { cn } from '@/lib/utils'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((state) => state.login)
  const register = useAuthStore((state) => state.register)
  const isLoading = useAuthStore((state) => state.isLoading)
  const error = useAuthStore((state) => state.error)
  const clearError = useAuthStore((state) => state.clearError)
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const from = (location.state as { from?: string } | null)?.from || '/chat'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    clearError()
    const ok = isRegister
      ? await register(username, password, email, phone)
      : await login(username, password)
    if (ok) {
      toast.success(isRegister ? '注册成功，游客购物车已合并' : '登录成功，欢迎回来')
      navigate(from, { replace: true })
    }
  }

  const passwordScore = [password.length >= 8, /[A-Za-z]/.test(password), /\d/.test(password)].filter(Boolean).length

  return (
    <main className="aurora-bg flex min-h-[100dvh] w-full overflow-x-hidden overflow-y-auto">
      <section className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-brand-gradient p-12 text-white lg:flex">
        <div className="absolute right-0 top-0 h-72 w-72 translate-x-1/3 -translate-y-1/3 rounded-full bg-white/10 blur-2xl" />
        <div className="relative flex items-center gap-2.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur"><Omi size={34} /></div>
          <span className="text-xl font-bold">{APP_NAME}</span>
        </div>
        <div className="relative">
          <OmiHero variant="login" className="mb-4" />
          <h1 className="text-4xl font-bold leading-tight">嗨，我是{AGENT_NAME}<br />你的购物智能体</h1>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-white/80">聊需求、传图片、说一句话，欧米结合真实评价与官方信息，帮你挑到对的那一件。</p>
        </div>
        <p className="relative text-sm text-white/70">多模态检索 · 决策可解释 · 长期偏好记忆</p>
      </section>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="p-4 lg:hidden">
          <button aria-label="返回聊天" onClick={() => navigate('/chat')} className="focus-ring flex h-10 w-10 items-center justify-center rounded-xl text-ink-soft hover:bg-[var(--surface-variant)]"><ArrowLeft size={20} /></button>
        </div>
        <div className="flex flex-1 items-center justify-center px-6 pb-10">
          <form className="w-full max-w-sm" onSubmit={submit} noValidate={false}>
            <OmiHero variant="login" size="compact" className="mb-2 justify-center lg:hidden" />
            <h2 className="text-2xl font-bold text-ink">{isRegister ? '创建账号' : '欢迎回来'}</h2>
            <p className="mt-1 text-sm text-ink-muted">{isRegister ? `注册后开启专属 ${AGENT_NAME} 购物体验` : '登录以同步你的购物车与偏好'}</p>

            <div className="mt-6 space-y-3">
              <Field id="username" name="username" label="用户名" icon={<User size={18} />} value={username} onChange={setUsername} autoComplete="username" minLength={2} required />
              <Field id="password" name="password" label="密码" icon={<Lock size={18} />} value={password} onChange={setPassword} type={showPassword ? 'text' : 'password'} autoComplete={isRegister ? 'new-password' : 'current-password'} minLength={isRegister ? 8 : undefined} required trailing={<button aria-label={showPassword ? '隐藏密码' : '显示密码'} onClick={() => setShowPassword((value) => !value)} className="focus-ring rounded-md text-ink-muted hover:text-ink" type="button">{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button>} />
              {isRegister && (
                <>
                  <div aria-label={`密码强度 ${passwordScore} / 3`} className="flex gap-1">{[1, 2, 3].map((level) => <span key={level} className={cn('h-1 flex-1 rounded-full', passwordScore >= level ? 'bg-brand-500' : 'bg-[var(--line)]')} />)}</div>
                  <Field id="email" name="email" label="邮箱（选填）" icon={<Mail size={18} />} value={email} onChange={setEmail} type="email" autoComplete="email" />
                  <Field id="phone" name="phone" label="手机号（选填）" icon={<Phone size={18} />} value={phone} onChange={setPhone} type="tel" autoComplete="tel" pattern="[0-9+ -]{6,20}" />
                </>
              )}
            </div>
            {error && <p className="mt-3 text-sm text-rose-500" role="alert">{error}</p>}
            <button disabled={isLoading} className="btn-primary mt-5 flex w-full justify-center py-3 text-base" type="submit">{isLoading ? <Spinner size={20} className="text-white" /> : isRegister ? '注册' : '登录'}</button>
            <p className="mt-4 text-center text-sm text-ink-muted">{isRegister ? '已有账号？' : '还没有账号？'}<button type="button" onClick={() => { setIsRegister((value) => !value); clearError() }} className="focus-ring ml-1 rounded font-medium text-brand-600 hover:underline">{isRegister ? '去登录' : '免费注册'}</button></p>
            <button type="button" onClick={() => navigate('/chat')} className="focus-ring mt-6 w-full rounded text-center text-sm text-ink-muted hover:text-ink">先随便逛逛 →</button>
          </form>
        </div>
      </section>
    </main>
  )
}

interface FieldProps {
  id: string; name: string; label: string; icon: ReactNode; value: string; onChange: (value: string) => void
  type?: string; trailing?: ReactNode; autoComplete?: string; minLength?: number; pattern?: string; required?: boolean
}

function Field({ id, name, label, icon, value, onChange, type = 'text', trailing, ...inputProps }: FieldProps) {
  return (
    <label htmlFor={id} className="block text-sm font-medium text-ink-soft">
      <span className="mb-1.5 block">{label}</span>
      <span className="flex items-center gap-2.5 rounded-xl border border-[var(--field-border)] bg-[var(--surface)] px-3.5 py-3 shadow-sm transition focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-500/10">
        <span className="text-ink-muted" aria-hidden>{icon}</span>
        <input id={id} name={name} type={type} value={value} onChange={(event) => onChange(event.target.value)} className="w-full bg-transparent text-[15px] outline-none" {...inputProps} />
        {trailing}
      </span>
    </label>
  )
}
