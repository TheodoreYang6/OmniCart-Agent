import { Moon, Sun } from 'lucide-react'
import { useThemeStore } from '@/store/themeStore'
import { cn } from '@/lib/utils'

/**
 * 主题切换开关（P0）——浅色 / 深色影院模式。
 * 双档滑块：拨到右侧为深色。图标随态高亮，切换有 200ms 过渡。
 */
export function ThemeToggle({ className }: { className?: string }) {
  const theme = useThemeStore((s) => s.theme)
  const toggle = useThemeStore((s) => s.toggle)
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? '切换到浅色模式' : '切换到深色模式'}
      title={isDark ? '浅色模式' : '深色影院模式'}
      className={cn(
        'relative inline-flex h-8 w-[58px] shrink-0 items-center rounded-full p-1',
        'border border-[var(--field-border)] bg-[var(--field-bg)] backdrop-blur transition-colors',
        className,
      )}
    >
      {/* 滑块 */}
      <span
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-full shadow-sm transition-transform duration-200 ease-out',
          'bg-white text-brand-500',
          isDark && 'translate-x-[26px] bg-brand-500 text-white',
        )}
      >
        {isDark ? <Moon size={14} /> : <Sun size={14} />}
      </span>
      {/* 底层双图标提示 */}
      <Sun
        size={13}
        className={cn(
          'pointer-events-none absolute left-2 text-ink-muted transition-opacity',
          isDark ? 'opacity-40' : 'opacity-0',
        )}
      />
      <Moon
        size={13}
        className={cn(
          'pointer-events-none absolute right-2 text-ink-muted transition-opacity',
          isDark ? 'opacity-0' : 'opacity-50',
        )}
      />
    </button>
  )
}
