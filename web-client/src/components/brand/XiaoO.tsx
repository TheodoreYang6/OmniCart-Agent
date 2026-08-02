import { cn } from '@/lib/utils'

/**
 * 小O (Xiao O) — OmniCart-agent 智能导购助手吉祥物。
 *
 * 依据「小O」设计稿实现的矢量形象：纯净白圆润机身 + 科技蓝配色 +
 * 未来屏幕脸 + 头顶 O 形天线 + 胸前 O 标志。可缩放、可切换表情，
 * 用于头像 / 品牌 Logo / 空状态插画等。
 *
 * 配色: 科技蓝 #256BFF / 浅蓝 #7DD3FC / 屏幕深蓝 #0D1B2A / 纯净白 #FFFFFF
 */

export type XiaoOExpression = 'happy' | 'wink' | 'thinking' | 'sleepy' | 'search'

/** 会话相位（ChatPage phase 直连）：thinking 光环呼吸 / talking 轻弹跳 */
export type XiaoOPhase = 'idle' | 'thinking' | 'talking'

interface XiaoOProps {
  size?: number
  expression?: XiaoOExpression
  /** 显示身体（含胸前 O 与手臂），用于 hero / 大图；默认仅头部，适合头像 */
  withBody?: boolean
  /** 轻微上下漂浮动画 */
  float?: boolean
  /** 相位驱动动效：thinking=光环呼吸，talking=轻弹跳 */
  phase?: XiaoOPhase
  className?: string
}

/** 带渐变光环的头像容器（玻璃拟态时代的品牌头像标准态） */
export function XiaoOAvatar({
  size = 36,
  phase = 'idle',
  expression,
  className,
}: {
  size?: number
  phase?: XiaoOPhase
  expression?: XiaoOExpression
  className?: string
}) {
  const exp: XiaoOExpression = expression ?? (phase === 'thinking' ? 'thinking' : 'happy')
  return (
    <div
      className={cn(
        'relative flex shrink-0 items-center justify-center rounded-full bg-white/90 ring-2 ring-brand-100 transition-shadow',
        phase === 'thinking' && 'animate-pulse-glow ring-brand-300',
        phase === 'talking' && 'animate-bounce-soft shadow-glow',
        className,
      )}
      style={{ width: size + 10, height: size + 10 }}
    >
      {/* 渐变描边光环 */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-full"
        style={{
          padding: 1.5,
          background: 'linear-gradient(135deg, #256BFF, #7DD3FC)',
          WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
        }}
      />
      <XiaoO size={size} expression={exp} />
    </div>
  )
}

export function XiaoO({
  size = 40,
  expression = 'happy',
  withBody = false,
  float = false,
  phase,
  className,
}: XiaoOProps) {
  const vb = withBody ? '0 0 120 150' : '0 0 120 122'
  const h = withBody ? size * (150 / 120) : size * (122 / 120)

  return (
    <svg
      width={size}
      height={h}
      viewBox={vb}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn(float && 'xo-float', phase === 'talking' && 'animate-bounce-soft', className)}
      role="img"
      aria-label="小O"
    >
      <defs>
        <linearGradient id="xoEye" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9BE0FF" />
          <stop offset="1" stopColor="#3E8CFF" />
        </linearGradient>
        <radialGradient id="xoScreen" cx="0.5" cy="0.4" r="0.75">
          <stop offset="0" stopColor="#16263B" />
          <stop offset="1" stopColor="#0D1B2A" />
        </radialGradient>
      </defs>

      {/* 天线：O 形环 + 连杆 */}
      <circle cx="60" cy="11" r="7" stroke="#256BFF" strokeWidth="4" />
      <rect x="57" y="17" width="6" height="14" rx="3" fill="#256BFF" />

      {/* 身体（可选） */}
      {withBody && (
        <g>
          <rect x="38" y="104" width="44" height="40" rx="20" fill="#FFFFFF" stroke="#E3EAF5" strokeWidth="2" />
          {/* 胸前 O 标志 */}
          <circle cx="60" cy="124" r="8" stroke="#256BFF" strokeWidth="3.5" />
          {/* 手臂 */}
          <rect x="24" y="108" width="16" height="9" rx="4.5" fill="#256BFF" transform="rotate(-18 32 112)" />
          <rect x="80" y="108" width="16" height="9" rx="4.5" fill="#256BFF" transform="rotate(18 88 112)" />
        </g>
      )}

      {/* 耳机/耳朵 */}
      <rect x="9" y="54" width="15" height="30" rx="7.5" fill="#256BFF" />
      <rect x="96" y="54" width="15" height="30" rx="7.5" fill="#256BFF" />

      {/* 头部 */}
      <rect x="20" y="28" width="80" height="78" rx="39" fill="#FFFFFF" stroke="#E3EAF5" strokeWidth="2" />
      {/* 顶部高光 */}
      <ellipse cx="48" cy="44" rx="20" ry="9" fill="#F2F6FF" opacity="0.8" />

      {/* 屏幕脸 */}
      <rect x="30" y="45" width="60" height="47" rx="23" fill="url(#xoScreen)" />

      {/* 表情 */}
      <Face expression={expression} />
    </svg>
  )
}

function Face({ expression }: { expression: XiaoOExpression }) {
  const eyeFill = 'url(#xoEye)'

  if (expression === 'wink') {
    return (
      <g>
        <rect x="43" y="60" width="9" height="16" rx="4.5" fill={eyeFill} />
        <path d="M67 69 Q72 64 78 69" stroke="#9BE0FF" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <path d="M53 82 Q60 89 67 82" stroke="#7DD3FC" strokeWidth="3.5" strokeLinecap="round" fill="none" />
      </g>
    )
  }

  if (expression === 'thinking') {
    return (
      <g>
        <circle cx="48" cy="66" r="4.5" fill={eyeFill} />
        <circle cx="72" cy="66" r="4.5" fill={eyeFill} />
        <path d="M55 82 Q60 85 65 82" stroke="#7DD3FC" strokeWidth="3" strokeLinecap="round" fill="none" />
        <text x="82" y="52" fill="#7DD3FC" fontSize="14" fontWeight="700">?</text>
      </g>
    )
  }

  if (expression === 'sleepy') {
    return (
      <g>
        <path d="M43 68 Q48 72 53 68" stroke="#9BE0FF" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <path d="M67 68 Q72 72 77 68" stroke="#9BE0FF" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        <path d="M55 83 Q60 86 65 83" stroke="#7DD3FC" strokeWidth="3" strokeLinecap="round" fill="none" />
        <text x="80" y="50" fill="#7DD3FC" fontSize="12" fontWeight="700">z</text>
      </g>
    )
  }

  if (expression === 'search') {
    return (
      <g>
        <rect x="43" y="60" width="9" height="16" rx="4.5" fill={eyeFill} />
        <rect x="68" y="60" width="9" height="16" rx="4.5" fill={eyeFill} />
        <path d="M53 82 Q60 88 67 82" stroke="#7DD3FC" strokeWidth="3.5" strokeLinecap="round" fill="none" />
        {/* 放大镜 */}
        <circle cx="86" cy="40" r="6" stroke="#256BFF" strokeWidth="3" fill="#F2F6FF" />
        <rect x="90" y="44" width="8" height="3.5" rx="1.75" fill="#256BFF" transform="rotate(45 90 44)" />
      </g>
    )
  }

  // happy / default
  return (
    <g>
      <rect x="43" y="59" width="9" height="17" rx="4.5" fill={eyeFill} />
      <rect x="68" y="59" width="9" height="17" rx="4.5" fill={eyeFill} />
      <path d="M52 82 Q60 90 68 82" stroke="#7DD3FC" strokeWidth="3.5" strokeLinecap="round" fill="none" />
    </g>
  )
}
