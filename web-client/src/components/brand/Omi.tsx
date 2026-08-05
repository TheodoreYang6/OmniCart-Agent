import { useEffect, useId, useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * 欧米 (Omi) — OmniCart-agent 品牌吉祥物，一只购物智能体猫。
 *
 * 与「欧米」（机器人，系统身份）形成双吉祥物分工：
 *   欧米  = 品牌的脸（Logo / 消息头像 / 正式署名），冷调纯白 + 科技蓝
 *   欧米 = 产品的心情（状态 / 空态 / 成功反馈 / 彩蛋 / 表情包），暖调奶油白 + 粉 + 同款蓝
 *
 * 共享品牌 DNA：耳内、瞳孔、尾尖、额头 O 印记均用 #256BFF → #7DD3FC 渐变，
 * 与 .gradient-brand 同源；粉色只出现在角色自身（腮红/鼻/爪垫），不进入 UI 色板。
 *
 * 配色: 奶油白 #FDF6EC / 暖灰描边 #E8DFD3 / 科技蓝 #256BFF / 浅蓝 #7DD3FC
 *       樱花粉 #FFC9CE / 蜜桃粉 #FF9FAE / 爪垫粉 #FFD4D9
 *
 * API 与 XiaoO 完全对齐（size / expression / withBody / float / phase），
 * 便于任意位置零成本替换或并用。
 */

export type OmiExpression =
  | 'happy'      // 开心笑 —— 回答完成
  | 'star'       // 星星眼 —— 发现高分好物
  | 'thinking'   // 思考中 —— 检索/推理阶段
  | 'wink'       // 眨眼 —— 加购/下单成功
  | 'sleepy'     // 打瞌睡 —— 空闲态
  | 'search'     // 搜索中 —— 深度思考多轮检索
  | 'surprised'  // 惊讶 —— 零结果 / 无匹配
  | 'pleading'   // 撒娇 —— 引导登录 / 请求补充需求
  | 'smug'       // 得意 —— 订单完成

/** 会话相位（与 XiaoOPhase 同构）：thinking 光环呼吸 / talking 轻弹跳 */
export type OmiPhase = 'idle' | 'thinking' | 'talking'

export type OmiVisualState =
  | 'idle' | 'listening' | 'searching' | 'analyzing' | 'talking'
  | 'highScore' | 'added' | 'ordered' | 'error' | 'login'

/** Product-wide state vocabulary so every Omi instance tells the same visual story. */
export const OMI_VISUAL_STATES: Record<OmiVisualState, { expression: OmiExpression; phase: OmiPhase }> = {
  idle: { expression: 'happy', phase: 'idle' },
  listening: { expression: 'pleading', phase: 'idle' },
  searching: { expression: 'search', phase: 'thinking' },
  analyzing: { expression: 'thinking', phase: 'thinking' },
  talking: { expression: 'happy', phase: 'talking' },
  highScore: { expression: 'star', phase: 'idle' },
  added: { expression: 'wink', phase: 'idle' },
  ordered: { expression: 'smug', phase: 'idle' },
  error: { expression: 'surprised', phase: 'idle' },
  login: { expression: 'pleading', phase: 'idle' },
}

interface OmiProps {
  size?: number
  expression?: OmiExpression
  /** 显示身体（含围巾、前爪、尾巴、购物袋），用于 hero / 空状态插画；默认仅头部，适合头像 */
  withBody?: boolean
  /** 轻微上下漂浮动画 */
  float?: boolean
  /** 相位驱动动效：thinking=尾尖呼吸，talking=轻弹跳 */
  phase?: OmiPhase
  className?: string
  /** Decorative instances stay silent; semantic instances announce the supplied label once. */
  decorative?: boolean
  label?: string
  /** Enable timer-driven blinking only for a prominent, active instance. */
  animated?: boolean
}

const CREAM = '#FDF6EC'
const OUTLINE = '#E8DFD3'
const TABBY = '#C3D6E8'      // 头顶虎斑纹（蓝灰）
const WHISKER = '#D8E4EF'    // 胡须
const BLUSH = '#FFC9CE'
const NOSE = '#FF9FAE'
const PAW = '#A8CFF5'      // 爪垫（淡蓝，对齐 3D 主视觉）
const BRAND = '#256BFF'
const MOUTH = '#A9705F'

/** 带渐变光环的头像容器（与 XiaoOAvatar 同规格，可直接互换） */
export function OmiAvatar({
  size = 36,
  phase = 'idle',
  expression,
  className,
}: {
  size?: number
  phase?: OmiPhase
  expression?: OmiExpression
  className?: string
}) {
  const exp: OmiExpression = expression ?? (phase === 'thinking' ? 'thinking' : 'happy')
  return (
    <div
      className={cn(
        // 光环改由 .omi-ring 伪元素提供（柔和渐变描边），取代原来的硬边 ring-brand-100；
        // thinking 换成 conic 旋转光环，talking 用柔和呼吸缩放而非上下弹跳
        'omi-ring relative flex shrink-0 items-center justify-center rounded-full bg-[var(--glass-bg-strong)] transition-shadow',
        phase === 'thinking' && 'omi-ring-spin shadow-glow',
        phase === 'talking' && 'omi-talk shadow-glow',
        className,
      )}
      style={{ width: size + 10, height: size + 10 }}
    >
      <Omi size={size} expression={exp} animated={phase !== 'idle'} />
    </div>
  )
}

export function Omi({
  size = 40,
  expression = 'happy',
  withBody = false,
  float = false,
  phase,
  className,
  decorative = true,
  label = '欧米',
  animated = false,
}: OmiProps) {
  const idBase = useId().replace(/:/g, '')
  const ids = {
    ear: `${idBase}-ear`, eye: `${idBase}-eye`, tail: `${idBase}-tail`, glow: `${idBase}-glow`,
  }
  const vb = withBody ? '0 0 120 152' : '0 0 120 112'
  const h = withBody ? size * (152 / 120) : size * (112 / 120)
  // 自动眨眼：只排除本身就是“闭眼语义”的两个表情——
  // wink 是单眼有意闭合、sleepy 是睡着，叠眨眼会破坏含义。
  // happy/smug 虽是月牙笑眼，但它们正是 idle 默认表情，不眨就等于
  // “让静态头像有生命感”完全落空（用户经常看到的就是 idle 态）。
  const blinkable = !['wink', 'sleepy'].includes(expression)
  const blinking = useAutoBlink(animated && blinkable)
  // talking 不再用 bounce-soft 的上下硬弹，统一走 .omi-talk 的柔和呼吸缩放

  return (
    <svg
      width={size}
      height={h}
      viewBox={vb}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn(float && 'xo-float', phase === 'talking' && 'omi-talk', className)}
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : label}
      aria-hidden={decorative || undefined}
    >
      <defs>
        <linearGradient id={ids.ear} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7DD3FC" />
          <stop offset="1" stopColor="#256BFF" />
        </linearGradient>
        <linearGradient id={ids.eye} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#4D8BFF" />
          <stop offset="1" stopColor="#1A54E8" />
        </linearGradient>
        <linearGradient id={ids.tail} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor={CREAM} />
          <stop offset="0.55" stopColor="#BFDCFF" />
          <stop offset="1" stopColor={BRAND} />
        </linearGradient>
        <radialGradient id={ids.glow} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#7DD3FC" stopOpacity="0.55" />
          <stop offset="1" stopColor="#7DD3FC" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* ---- 身体（可选）：先画，保证头部叠在最上 ---- */}
      {withBody && (
        <g>
          {/* 尾尖光晕（thinking 相位下呼吸） */}
          <circle
            cx="106" cy="110" r="18" fill={`url(#${ids.glow})`}
            className={phase === 'thinking' ? 'animate-breathe' : undefined}
          />
          {/* 尾巴：从右侧翘起，尾尖渐变为品牌蓝 */}
          <path
            d="M82 134 Q104 138 108 116 Q110 101 99 100"
            stroke={`url(#${ids.tail})`} strokeWidth="12" strokeLinecap="round" fill="none"
          />
          {/* 躯干 */}
          <ellipse cx="60" cy="126" rx="29" ry="22" fill={CREAM} stroke={OUTLINE} strokeWidth="2" />
          {/* 前爪（蓝色肉垫，对齐 3D 主视觉） */}
          <ellipse cx="45" cy="144" rx="9.5" ry="7" fill={CREAM} stroke={OUTLINE} strokeWidth="2" />
          <circle cx="45" cy="144" r="3.4" fill={PAW} />
          <ellipse cx="62" cy="146" rx="9.5" ry="7" fill={CREAM} stroke={OUTLINE} strokeWidth="2" />
          <circle cx="62" cy="146" r="3.4" fill={PAW} />
        </g>
      )}

      {/* ---- 耳朵：圆润三角 + 耳内品牌蓝渐变（最高识别度单点） ---- */}
      <path d="M27 47 Q13 6 55 31 Z" fill={CREAM} stroke={OUTLINE} strokeWidth="2" strokeLinejoin="round" />
      <path d="M34 42 Q25 21 47 32 Z" fill={`url(#${ids.ear})`} />
      <path d="M93 47 Q107 6 65 31 Z" fill={CREAM} stroke={OUTLINE} strokeWidth="2" strokeLinejoin="round" />
      <path d="M86 42 Q95 21 73 32 Z" fill={`url(#${ids.ear})`} />

      {/* ---- 头部：扁圆（圆度是萌感第一来源） ---- */}
      <ellipse cx="60" cy="66" rx="41" ry="34" fill={CREAM} stroke={OUTLINE} strokeWidth="2" />

      {/* 头顶虎斑纹 —— 让"白猫"有纹理记忆点，不是一团白（3D 主视觉同步特征） */}
      <g stroke={TABBY} strokeWidth="3" strokeLinecap="round" fill="none" opacity="0.9">
        <path d="M49 38 Q50 44 50 48" />
        <path d="M60 35 Q61 42 61 46" />
        <path d="M71 38 Q70 44 70 48" />
      </g>

      {/* 额头不再放 O 印记 —— 身份改由项圈挂牌承载（猫戴项圈的语义更准，
          且挂牌天然带名字 omi，比额头印记更简洁） */}

      {/* 胡须 —— 猫的强特征，首版漏了 */}
      <g stroke={WHISKER} strokeWidth="1.6" strokeLinecap="round" fill="none">
        <path d="M22 68 L6 64" />
        <path d="M22 74 L5 75" />
        <path d="M98 68 L114 64" />
        <path d="M98 74 L115 75" />
      </g>

      {/* 腮红 */}
      <ellipse cx="29" cy="72" rx="8" ry="5.2" fill={BLUSH} opacity="0.85" />
      <ellipse cx="91" cy="72" rx="8" ry="5.2" fill={BLUSH} opacity="0.85" />

      {/* 表情 */}
      <OmiFace expression={expression} blinking={blinking} eyeId={ids.eye} />

      {/* 围巾（仅 withBody 时接到脖子） */}
      {withBody && (
        <g>
          {/* 项圈带 */}
          <path
            d="M40 95 Q60 106 80 95"
            stroke={BRAND} strokeWidth="6" strokeLinecap="round" fill="none"
          />
          {/* omi 挂牌 —— 身份标识（对齐 3D 主视觉，天然带名字） */}
          <circle cx="60" cy="111" r="10" fill="#BFDCFF" stroke={BRAND} strokeWidth="1.6" />
          <text
            x="60" y="114.5" textAnchor="middle"
            fill={BRAND} fontSize="8" fontWeight="700"
            fontFamily="system-ui, -apple-system, sans-serif"
          >
            omi
          </text>
        </g>
      )}
    </svg>
  )
}

/** 自动眨眼：随机 3~6s 眨一次，120ms 后回弹，让静态头像有生命感。
 *  reduced-motion 下不启用。 */
function useAutoBlink(enabled: boolean) {
  const [blinking, setBlinking] = useState(false)

  useEffect(() => {
    if (!enabled) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let alive = true
    const timers: number[] = []
    const schedule = () => {
      if (!alive) return
      timers.push(
        window.setTimeout(() => {
          if (!alive) return
          setBlinking(true)
          timers.push(
            window.setTimeout(() => {
              if (!alive) return
              setBlinking(false)
              schedule()
            }, 120),
          )
        }, 3000 + Math.random() * 3000),
      )
    }
    schedule()
    return () => {
      alive = false
      timers.forEach(clearTimeout)
    }
  }, [enabled])

  return blinking
}

/** 鼻 + 嘴（ω 形）—— 多数表情共用 */
function NoseMouth({ open = false }: { open?: boolean }) {
  return (
    <g>
      <path d="M56 72 Q60 69 64 66 Q60 76 56 66 Z" fill={NOSE} />
      {open ? (
        <path d="M52 78 Q60 90 68 72 Q60 82 52 72 Z" fill={MOUTH} />
      ) : (
        <g stroke={MOUTH} strokeWidth="2" strokeLinecap="round" fill="none">
          <path d="M60 76 Q55 82 51 71" />
          <path d="M60 76 Q65 82 69 71" />
        </g>
      )}
    </g>
  )
}

/** 表情容器：交叉淡化 + 眨眼眼睑。
 *
 *  只保留「当前 + 上一个」两层（而非 9 个表情全部常驻 DOM）：
 *  新表情先画在底层，旧表情后画在上层并淡出，形成自然的交叉渐变。
 */
function OmiFace({
  expression,
  blinking,
  eyeId,
}: {
  expression: OmiExpression
  blinking?: boolean
  eyeId: string
}) {
  const [cur, setCur] = useState(expression)
  const [fading, setFading] = useState<OmiExpression | null>(null)

  useEffect(() => {
    if (expression === cur) return
    setFading(cur)
    setCur(expression)
    const t = window.setTimeout(() => setFading(null), 260)
    return () => clearTimeout(t)
  }, [expression, cur])

  return (
    <g>
      <FaceContent expression={cur} eyeId={eyeId} />
      {fading && (
        <g key={fading} className="omi-face-out">
          <FaceContent expression={fading} eyeId={eyeId} />
        </g>
      )}
      {blinking && <Eyelids eyeId={eyeId} />}
    </g>
  )
}

/** 眨眼眼睑：用毛色椭圆盖住眼睛 + 一道闭合眼缝，对所有表情通用。
 *  （比缩放眼睛本体更简单：眼睛分散在各表情层内部，不好统一变换）*/
function Eyelids({ eyeId }: { eyeId: string }) {
  return (
    <g>
      <ellipse cx="44" cy="63" rx="9.6" ry="10.6" fill={CREAM} />
      <ellipse cx="76" cy="63" rx="9.6" ry="10.6" fill={CREAM} />
      <g stroke={`url(#${eyeId})`} strokeWidth="2.6" strokeLinecap="round" fill="none">
        <path d="M37 63 Q44 68 51 62" />
        <path d="M69 63 Q76 68 83 62" />
      </g>
    </g>
  )
}

function FaceContent({ expression, eyeId }: { expression: OmiExpression; eyeId: string }) {
  const eye = `url(#${eyeId})`

  // 圆眼 + 双高光（默认眼型）
  const roundEyes = (
    <g>
      <ellipse cx="44" cy="63" rx="8" ry="9" fill={eye} />
      <ellipse cx="76" cy="63" rx="8" ry="9" fill={eye} />
      <circle cx="41.5" cy="59.5" r="2.8" fill="#FFFFFF" />
      <circle cx="73.5" cy="59.5" r="2.8" fill="#FFFFFF" />
      <circle cx="46.5" cy="67" r="1.4" fill="#FFFFFF" opacity="0.8" />
      <circle cx="78.5" cy="67" r="1.4" fill="#FFFFFF" opacity="0.8" />
    </g>
  )

  // 月牙笑眼
  const smileEyes = (
    <g stroke={eye} strokeWidth="3.6" strokeLinecap="round" fill="none">
      <path d="M37 64 Q44 56 51 58" />
      <path d="M69 64 Q76 56 83 58" />
    </g>
  )

  if (expression === 'happy') {
    return (
      <g>
        {smileEyes}
        <NoseMouth open />
      </g>
    )
  }

  if (expression === 'star') {
    // 星星眼 —— 发现好物的招牌表情
    return (
      <g>
        <Star cx={44} cy={63} eyeId={eyeId} />
        <Star cx={76} cy={63} eyeId={eyeId} />
        <NoseMouth open />
      </g>
    )
  }

  if (expression === 'thinking') {
    return (
      <g>
        {/* 眼睛向上看 */}
        <ellipse cx="44" cy="61" rx="7.5" ry="8.5" fill={eye} />
        <ellipse cx="76" cy="61" rx="7.5" ry="8.5" fill={eye} />
        <circle cx="45" cy="57" r="2.6" fill="#FFFFFF" />
        <circle cx="77" cy="57" r="2.6" fill="#FFFFFF" />
        <NoseMouth />
        {/* 头顶三点 */}
        <g fill="#7DD3FC">
          <circle cx="46" cy="22" r="2.6" />
          <circle cx="60" cy="18" r="2.6" />
          <circle cx="74" cy="22" r="2.6" />
        </g>
      </g>
    )
  }

  if (expression === 'wink') {
    return (
      <g>
        <path d="M37 63 Q44 56 51 57" stroke={eye} strokeWidth="3.6" strokeLinecap="round" fill="none" />
        <ellipse cx="76" cy="63" rx="8" ry="9" fill={eye} />
        <circle cx="73.5" cy="59.5" r="2.8" fill="#FFFFFF" />
        <NoseMouth open />
      </g>
    )
  }

  if (expression === 'sleepy') {
    return (
      <g>
        <g stroke={eye} strokeWidth="3.4" strokeLinecap="round" fill="none">
          <path d="M37 64 Q44 70 51 58" />
          <path d="M69 64 Q76 70 83 58" />
        </g>
        <NoseMouth />
        <text x="86" y="30" fill="#7DD3FC" fontSize="15" fontWeight="800">z</text>
        <text x="97" y="21" fill="#7DD3FC" fontSize="10" fontWeight="800" opacity="0.7">z</text>
      </g>
    )
  }

  if (expression === 'search') {
    return (
      <g>
        {roundEyes}
        <NoseMouth />
        {/* 放大镜 */}
        <circle cx="93" cy="52" r="9" stroke={BRAND} strokeWidth="3" fill="#EAF1FF" fillOpacity="0.7" />
        <path d="M99 59 L107 67" stroke={BRAND} strokeWidth="3.5" strokeLinecap="round" />
      </g>
    )
  }

  if (expression === 'surprised') {
    return (
      <g>
        <ellipse cx="44" cy="63" rx="9" ry="10" fill="#FFFFFF" stroke={eye} strokeWidth="2.4" />
        <ellipse cx="76" cy="63" rx="9" ry="10" fill="#FFFFFF" stroke={eye} strokeWidth="2.4" />
        <circle cx="44" cy="63" r="3.4" fill={eye} />
        <circle cx="76" cy="63" r="3.4" fill={eye} />
        <path d="M56 72 Q60 69 64 66 Q60 76 56 66 Z" fill={NOSE} />
        <ellipse cx="60" cy="82" rx="4" ry="5" fill={MOUTH} />
      </g>
    )
  }

  if (expression === 'pleading') {
    // 撒娇：水汪汪大眼 + 眉毛下垂
    return (
      <g>
        <ellipse cx="44" cy="64" rx="9.5" ry="10.5" fill={eye} />
        <ellipse cx="76" cy="64" rx="9.5" ry="10.5" fill={eye} />
        <circle cx="41" cy="60" r="3.4" fill="#FFFFFF" />
        <circle cx="73" cy="60" r="3.4" fill="#FFFFFF" />
        <ellipse cx="47" cy="69" rx="2.6" ry="2" fill="#FFFFFF" opacity="0.9" />
        <ellipse cx="79" cy="69" rx="2.6" ry="2" fill="#FFFFFF" opacity="0.9" />
        <g stroke={OUTLINE} strokeWidth="2.2" strokeLinecap="round" fill="none">
          <path d="M35 50 Q42 47 49 45" />
          <path d="M85 50 Q78 47 71 45" />
        </g>
        <path d="M56 74 Q60 71 64 68 Q60 78 56 68 Z" fill={NOSE} />
        <path d="M56 82 Q60 85 64 76" stroke={MOUTH} strokeWidth="2" strokeLinecap="round" fill="none" />
      </g>
    )
  }

  // smug 得意
  return (
    <g>
      <g stroke={eye} strokeWidth="3.6" strokeLinecap="round" fill="none">
        <path d="M37 65 Q44 58 51 59" />
        <path d="M69 65 Q76 58 83 59" />
      </g>
      <path d="M56 72 Q60 69 64 66 Q60 76 56 66 Z" fill={NOSE} />
      <path d="M53 78 Q60 85 67 72" stroke={MOUTH} strokeWidth="2.2" strokeLinecap="round" fill="none" />
    </g>
  )
}

/** 四角星（星星眼） */
function Star({ cx, cy, eyeId }: { cx: number; cy: number; eyeId: string }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r="8" fill={`url(#${eyeId})`} />
      <path
        d={`M${cx} ${cy - 7} Q${cx + 1.4} ${cy - 1.4} ${cx + 7} ${cy} Q${cx + 1.4} ${cy + 1.4} ${cx} ${cy + 7} Q${cx - 1.4} ${cy + 1.4} ${cx - 7} ${cy} Q${cx - 1.4} ${cy - 1.4} ${cx} ${cy - 7} Z`}
        fill="#FFFFFF"
      />
    </g>
  )
}
