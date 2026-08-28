import { cn } from '@/lib/utils'
import { useThemeStore } from '@/store/themeStore'

type OmiAppIconPhase = 'idle' | 'thinking' | 'talking'

interface OmiAppIconProps {
  size?: number
  phase?: OmiAppIconPhase
  shape?: 'circle' | 'squircle'
  className?: string
  decorative?: boolean
  label?: string
}

/**
 * 欧米移动端图标的 UI 版本。浅、深色品牌标随全局主题成对切换。
 */
export function OmiAppIcon({
  size = 44,
  phase = 'idle',
  shape = 'squircle',
  className,
  decorative = true,
  label = '欧米购物智能体',
}: OmiAppIconProps) {
  const theme = useThemeStore((state) => state.theme)
  return (
    <span
      className={cn(
        'omi-app-icon relative isolate inline-flex shrink-0 items-center justify-center overflow-hidden',
        shape === 'circle' ? 'rounded-full' : 'rounded-[30%]',
        phase === 'thinking' && 'omi-app-icon-thinking shadow-glow',
        phase === 'talking' && 'omi-talk shadow-glow',
        className,
      )}
      style={{ width: size, height: size }}
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : label}
      aria-hidden={decorative || undefined}
    >
      <img
        src={theme === 'dark' ? '/brand/omi-logo-dark.png' : '/brand/omi-logo-light.png'}
        alt=""
        width="256"
        height="256"
        draggable={false}
        className="relative z-[1] h-full w-full select-none object-cover"
      />
    </span>
  )
}
