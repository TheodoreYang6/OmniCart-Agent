import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  /** center: 居中弹窗（桌面）；bottom: 底部抽屉（移动优先）；right: 右侧抽屉 */
  variant?: 'center' | 'bottom' | 'right'
  className?: string
  hideClose?: boolean
}

/**
 * 通用弹层，通过 Portal 渲染到 body。
 * 响应式：默认 center 弹窗，bottom 用于移动端底部抽屉。
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  variant = 'center',
  className,
  hideClose,
}: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  const panelPos =
    variant === 'bottom'
      ? 'items-end sm:items-center'
      : variant === 'right'
        ? 'items-stretch justify-end'
        : 'items-center justify-center'

  const panelAnim =
    variant === 'right' ? 'animate-slide-up sm:animate-fade-in' : 'animate-scale-in'

  const panelShape =
    variant === 'bottom'
      ? 'w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl'
      : variant === 'right'
        ? 'h-full w-full max-w-md rounded-l-2xl'
        : 'w-full max-w-lg rounded-2xl'

  return createPortal(
    <div className={cn('fixed inset-0 z-[90] flex p-0 sm:p-4', panelPos)}>
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />
      <div
        className={cn(
          'relative z-10 flex max-h-[92vh] flex-col overflow-hidden bg-[var(--surface)] shadow-float',
          panelShape,
          panelAnim,
          className,
        )}
      >
        {(title || !hideClose) && (
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-3.5">
            <h3 className="text-base font-semibold text-ink">{title}</h3>
            {!hideClose && (
              <button
                onClick={onClose}
                className="rounded-lg p-1.5 text-ink-muted transition hover:bg-[var(--surface-variant)] hover:text-ink"
                aria-label="关闭"
              >
                <X size={20} />
              </button>
            )}
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
