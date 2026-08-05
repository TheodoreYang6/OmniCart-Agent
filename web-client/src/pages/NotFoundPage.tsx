import { ArrowLeft, Home } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Omi } from '@/components/brand/Omi'

export function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <main className="aurora-bg flex h-full items-center justify-center overflow-auto p-6">
      <section className="glass max-w-md p-8 text-center">
        <Omi size={112} expression="surprised" decorative />
        <p className="mt-3 text-sm font-semibold text-brand-600">404 · 走丢啦</p>
        <h1 className="mt-1 text-2xl font-extrabold text-ink">欧米没找到这个页面</h1>
        <p className="mt-2 text-sm text-ink-muted">链接可能已失效，也可能输入错了地址。</p>
        <div className="mt-6 flex justify-center gap-3">
          <button className="btn-secondary inline-flex items-center gap-2" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> 返回
          </button>
          <Link className="btn-primary inline-flex items-center gap-2" to="/chat">
            <Home size={16} /> 回到首页
          </Link>
        </div>
      </section>
    </main>
  )
}
