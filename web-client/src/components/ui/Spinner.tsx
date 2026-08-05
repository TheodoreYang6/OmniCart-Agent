import { cn } from '@/lib/utils'

export function Spinner({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={cn('animate-spin text-brand-500', className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="加载中"
    >
      <circle
        className="opacity-20"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  )
}

/** 居中的加载态。 */
export function LoadingBlock({ text }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-ink-muted">
      <Spinner size={28} />
      {text && <p className="text-sm">{text}</p>}
    </div>
  )
}

/** 三点跳动（AI 思考中）。 */
export function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-brand-400"
          style={{ animation: `blink 1.2s ${i * 0.2}s infinite` }}
        />
      ))}
    </span>
  )
}
