import { useEffect, useId, useRef, type ReactNode } from 'react'
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
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const titleId = useId()
  useEffect(() => {
    onCloseRef.current = onClose
  })
  useEffect(() => {
    if (!open) return
    const previousFocus = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    const panel = panelRef.current
    const focusable = () => Array.from(panel?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? [])
    const initialTarget = () => {
      const formField = panel?.querySelector<HTMLElement>(
        'input:not([disabled]), textarea:not([disabled]), select:not([disabled])',
      )
      return formField ?? focusable()[0] ?? panel
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCloseRef.current()
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items.length) {
        event.preventDefault()
        panel?.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    requestAnimationFrame(() => initialTarget()?.focus())
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      previousFocus?.focus()
    }
  }, [open])

  if (!open) return null

  const panelPos =
    variant === 'bottom'
      // Mobile keeps the natural bottom sheet.  On desktop a bottom sheet is
      // still a compact form dialog, so it must be centred on both axes; using
      // only ``items-center`` centred the vertical axis while flex kept it
      // pinned to the left edge.
      ? 'items-end sm:items-center sm:justify-center'
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
      <button
        type="button"
        tabIndex={-1}
        aria-label="关闭对话框"
        className="absolute inset-0 bg-ink/40 backdrop-blur-sm animate-fade-in"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : '对话框'}
        tabIndex={-1}
        className={cn(
          'relative z-10 flex max-h-[92vh] flex-col overflow-hidden bg-[var(--surface)] shadow-float',
          panelShape,
          panelAnim,
          className,
        )}
      >
        {(title || !hideClose) && (
          <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-3.5">
            <h3 id={titleId} className="text-base font-semibold text-ink">{title}</h3>
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
