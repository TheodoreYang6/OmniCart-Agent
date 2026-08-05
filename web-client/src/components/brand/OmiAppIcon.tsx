import { cn } from '@/lib/utils'

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
 * 欧米移动端图标的 UI 版本。
 * 猫与购物车使用透明素材，底板由主题色生成，因此会自然适配浅色和深色环境。
 */
export function OmiAppIcon({
  size = 44,
  phase = 'idle',
  shape = 'squircle',
  className,
  decorative = true,
  label = '欧米购物智能体',
}: OmiAppIconProps) {
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
        src="/brand/omi-cart-avatar-256-v2.webp"
        alt=""
        width="256"
        height="256"
        draggable={false}
        className="relative z-[1] h-[91%] w-[91%] select-none object-contain"
      />
    </span>
  )
}
