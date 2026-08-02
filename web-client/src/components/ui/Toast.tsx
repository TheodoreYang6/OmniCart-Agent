import { CheckCircle2, Info, XCircle } from 'lucide-react'
import { useToastStore } from '@/store/toastStore'
import { cn } from '@/lib/utils'

/** 全局 Toast 容器，挂载在 App 根部。 */
export function ToastHost() {
  const toasts = useToastStore((s) => s.toasts)

  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[100] flex flex-col items-center gap-2 px-4">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            'pointer-events-auto flex max-w-sm items-center gap-2.5 rounded-xl px-4 py-3 text-sm shadow-float animate-slide-up',
            t.kind === 'success' && 'bg-emerald-600 text-white',
            t.kind === 'error' && 'bg-rose-600 text-white',
            t.kind === 'info' && 'bg-ink text-white',
          )}
        >
          {t.kind === 'success' && <CheckCircle2 size={18} className="shrink-0" />}
          {t.kind === 'error' && <XCircle size={18} className="shrink-0" />}
          {t.kind === 'info' && <Info size={18} className="shrink-0" />}
          <span className="leading-snug">{t.message}</span>
        </div>
      ))}
    </div>
  )
}
