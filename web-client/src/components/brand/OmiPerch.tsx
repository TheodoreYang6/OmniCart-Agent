import { useCallback, useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * OmiPerch — 卧在标题上的欧米（3D 主视觉 + SVG 可动部件混合）。
 *
 * 为什么是混合而非纯 SVG 重绘：3D 渲染图的毛绒质感是首页的视觉资产，
 * 用扁平 SVG 重画会明显降级；但纯 PNG 又无法做眼神跟随这类逐部件交互。
 *
 * 眼神跟随的实现关键：这只猫的瞳孔是**大面积均匀黑**（实测 #0B1119 左右，
 * 占眼宽约 68%），虹膜只是一圈细边。所以在 PNG 之上补一层同色瞳孔椭圆，
 * 把 PNG 里的瞳孔和静态高光整块盖住，再整组平移 —— 位移半径限 3px，
 * 落在均匀黑区内不会露出接缝，也不会顶到眼睑。高光画在这一组内部，
 * 随瞳孔一起走，是眼神方向最强的视觉信号。
 *
 * 尾巴：**不要再补 SVG 尾巴**。猫身右侧那条粗大的毛筒就是尾巴本体 ——
 * 它从身后绕出、盘在身体前面，尾尖回勾向内（早期注释把它误读成“弯曲的
 * 后腿爪掌”，按那个误读在 PNG 下方又画了一条，结果是猫长了两条尾巴）。
 * 已有尾巴是烧在位图里的，无法单独旋转；要真的摆尾得把尾巴从素材里拆成
 * 独立图层并补画遮住的身体，不是叠一层 SVG 能解决的。
 *
 * 坐标全部来自对 public/brand/omi-perch-v4-640.png (640x559) 的像素级采样，
 * 与 SVG viewBox 一一对应；换素材需重新测量。
 */

/** 眼睛几何（viewBox 640x559 坐标系，实测值）
 *  pupil = PNG 里均匀黑瞳孔的外接椭圆（lum<40 连通域），略放大 1px 保证盖住；
 *  hl1 = PNG 原有主高光位置（shift=0 时同位覆盖，零痕迹）；hl2 = 副高光。 */
const EYES = [
  {
    lid: { cx: 211, cy: 240, rx: 30, ry: 25 },
    pupil: { cx: 210, cy: 242, rx: 21, ry: 18, fill: '#0B1119' },
    hl1: { x: 222, y: 229, r: 5.7 },
    hl2: { x: 202.5, y: 249.5, r: 2.3 },
  },
  {
    lid: { cx: 341, cy: 214, rx: 27, ry: 25 },
    pupil: { cx: 341, cy: 215, rx: 20, ry: 18, fill: '#0D131D' },
    hl1: { x: 352, y: 202, r: 5.8 },
    hl2: { x: 334, y: 222, r: 2.4 },
  },
] as const

/** 眼睑毛色（贴合眼周绒毛，用于眨眼覆盖） */
const LID = '#E9E6E4'
const LID_LINE = '#5B6472'

/** 瞳孔跟随的最大位移（viewBox 单位）。超过 3px 会露出瞳孔接缝并显得眼球脱框 */
const MAX_SHIFT = 3

/** 星星眼持续时长：点击后瞬时切星星眼，1.2s 自动回落 */
const STAR_MS = 1200

interface Heart {
  id: number
  dx: number
  rot: number
  delay: number
}

export function OmiPerch({
  className,
  interactive = true,
}: {
  className?: string
  interactive?: boolean
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const pupilRefs = useRef<Array<SVGGElement | null>>([])
  const timerRefs = useRef<number[]>([])
  const [blinking, setBlinking] = useState(false)
  const [starry, setStarry] = useState(false)
  const [hover, setHover] = useState(false)
  const [pop, setPop] = useState(false)
  const [hearts, setHearts] = useState<Heart[]>([])
  const [reduced, setReduced] = useState(false)
  const [visible, setVisible] = useState(true)
  const [finePointer, setFinePointer] = useState(false)

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const pointer = window.matchMedia('(hover: hover) and (pointer: fine)')
    const sync = () => {
      setReduced(motion.matches)
      setFinePointer(pointer.matches)
    }
    sync()
    motion.addEventListener('change', sync)
    pointer.addEventListener('change', sync)
    return () => {
      motion.removeEventListener('change', sync)
      pointer.removeEventListener('change', sync)
    }
  }, [])

  useEffect(() => {
    const node = wrapRef.current
    if (!node || !('IntersectionObserver' in window)) return
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      rootMargin: '80px',
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => () => timerRefs.current.forEach(clearTimeout), [])

  // 眼神跟随：指针方向 → 瞳孔位移（rAF 节流，避免每次 mousemove 都触发渲染）
  useEffect(() => {
    if (!interactive || reduced || !visible || !finePointer) return
    let raf = 0
    let pending: { x: number; y: number } | null = null

    const flush = () => {
      raf = 0
      if (!pending || !wrapRef.current) return
      const r = wrapRef.current.getBoundingClientRect()
      const cx = r.left + r.width * 0.45 // 猫脸重心略偏左
      const cy = r.top + r.height * 0.45
      const dx = pending.x - cx
      const dy = pending.y - cy
      const len = Math.hypot(dx, dy) || 1
      // 距离越近位移越小（贴到脸上时不至于眼球乱飘）
      const k = Math.min(1, len / 420)
      const x = ((dx / len) * MAX_SHIFT * k).toFixed(2)
      const y = ((dy / len) * MAX_SHIFT * k).toFixed(2)
      pupilRefs.current.forEach((pupil) => pupil?.setAttribute('transform', `translate(${x} ${y})`))
    }

    const onMove = (e: MouseEvent) => {
      pending = { x: e.clientX, y: e.clientY }
      if (!raf) raf = requestAnimationFrame(flush)
    }
    window.addEventListener('mousemove', onMove, { passive: true })
    return () => {
      window.removeEventListener('mousemove', onMove)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [finePointer, interactive, reduced, visible])

  // 随机眨眼（与头像系统同一套时序口径：3~6s 一次，120ms 闭合）
  useEffect(() => {
    if (!interactive || reduced || !visible) return
    let alive = true
    const timers: number[] = []
    const loop = () => {
      if (!alive) return
      timers.push(
        window.setTimeout(() => {
          if (!alive) return
          setBlinking(true)
          timers.push(
            window.setTimeout(() => {
              if (!alive) return
              setBlinking(false)
              loop()
            }, 130),
          )
        }, 2800 + Math.random() * 3200),
      )
    }
    loop()
    return () => {
      alive = false
      timers.forEach(clearTimeout)
    }
  }, [interactive, reduced, visible])

  // 点击：弹一下 + 冒三颗爱心 + 瞬时切星星眼（1.2s 后回落）
  const onPoke = useCallback(() => {
    if (!interactive) return
    if (reduced) {
      setStarry(true)
      const timer = window.setTimeout(() => setStarry(false), STAR_MS)
      timerRefs.current.push(timer)
      return
    }
    setPop(true)
    setStarry(true)
    timerRefs.current.push(window.setTimeout(() => setPop(false), 620))
    timerRefs.current.push(window.setTimeout(() => setStarry(false), STAR_MS))
    const base = Date.now()
    setHearts((prev) => [
      ...prev,
      ...[0, 1, 2].map((i) => ({
        id: base + i,
        dx: (i - 1) * 26 + (Math.random() * 12 - 6),
        rot: Math.random() * 40 - 20,
        delay: i * 90,
      })),
    ])
    timerRefs.current.push(window.setTimeout(() => {
      setHearts((prev) => prev.filter((h) => h.id < base))
    }, 1400))
  }, [interactive, reduced])

  return (
    <div
      ref={wrapRef}
      data-omi-perch=""
      className={cn(
        // z-10 让垂下的前爪盖在标题文字上沿，形成"搭在字上"的观感
        'relative z-10 select-none',
        className,
      )}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => {
        setHover(false)
        pupilRefs.current.forEach((pupil) => pupil?.setAttribute('transform', 'translate(0 0)'))
      }}
      onClick={onPoke}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onPoke()
        }
      }}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={interactive ? '和欧米互动' : undefined}
      aria-hidden={interactive ? undefined : true}
    >
      <div
        className={cn(
          'relative transition-transform duration-500 ease-out',
          hover && 'omi-perch-lift',
          pop && 'omi-perch-pop',
        )}
      >
        {/* 呼吸层单独一层：与 lift/pop 的 transform 分开，否则同一元素上会互相覆盖 */}
        <div className="omi-perch-breathe relative">
          <picture>
            <source
              type="image/avif"
              srcSet="/brand/omi-perch-v4-320.avif 320w, /brand/omi-perch-v4-640.avif 640w"
              sizes="(max-width: 640px) 176px, 256px"
            />
            <source
              type="image/webp"
              srcSet="/brand/omi-perch-v4-320.webp 320w, /brand/omi-perch-v4-640.webp 640w"
              sizes="(max-width: 640px) 176px, 256px"
            />
            <img
              src="/brand/omi-perch-v4.png"
              alt=""
              width="640"
              height="559"
              draggable={false}
              fetchPriority="high"
              className="relative block w-full"
            />
          </picture>

          {/* 可动部件覆盖层：与 PNG 同坐标系，绝对贴合（在 PNG 之上，盖住眼睛）*/}
          <svg
            viewBox="0 0 640 559"
            className="pointer-events-none absolute inset-0 z-10 h-full w-full"
            aria-hidden
          >
            {EYES.map((e, i) => (
              <g key={i}>
                {/* 瞳孔组：同色椭圆盖掉 PNG 的瞳孔与静态高光，整组平移做眼神跟随。
                    断言用：data-omi-pupil 上的 transform 会随 mousemove 变化。 */}
                <g
                  ref={(node) => { pupilRefs.current[i] = node }}
                  data-omi-pupil={i}
                  transform="translate(0 0)"
                >
                  <ellipse
                    cx={e.pupil.cx}
                    cy={e.pupil.cy}
                    rx={e.pupil.rx}
                    ry={e.pupil.ry}
                    fill={e.pupil.fill}
                  />
                  {starry ? (
                    // 星星眼：四角星画在瞳孔内，白色对深瞳孔对比最高
                    <StarEye cx={e.pupil.cx} cy={e.pupil.cy} r={e.pupil.ry * 0.92} />
                  ) : (
                    <>
                      <circle
                        cx={e.hl1.x}
                        cy={e.hl1.y}
                        r={e.hl1.r}
                        fill="#FFFFFF"
                        opacity={blinking ? 0 : 0.96}
                      />
                      <circle
                        cx={e.hl2.x}
                        cy={e.hl2.y}
                        r={e.hl2.r}
                        fill="#FFFFFF"
                        opacity={blinking ? 0 : 0.55}
                      />
                    </>
                  )}
                </g>
                {/* 眨眼：毛色眼睑盖住整只眼 + 一道闭合眼缝 */}
                {blinking && (
                  <g>
                    <ellipse
                      cx={e.lid.cx}
                      cy={e.lid.cy}
                      rx={e.lid.rx}
                      ry={e.lid.ry}
                      fill={LID}
                    />
                    <path
                      d={`M${e.lid.cx - e.lid.rx * 0.82} ${e.lid.cy} Q${e.lid.cx} ${e.lid.cy + e.lid.ry * 0.5} ${e.lid.cx + e.lid.rx * 0.82} ${e.lid.cy - e.lid.ry * 0.16}`}
                      stroke={LID_LINE}
                      strokeWidth="3"
                      strokeLinecap="round"
                      fill="none"
                      opacity="0.7"
                    />
                  </g>
                )}
              </g>
            ))}
          </svg>
        </div>

        {/* 点击爱心：从猫头上方冒出（贴项圈位置会被猫身遮挡，且像"吐爱心"）*/}
        {hearts.map((h) => (
          <span
            key={h.id}
            data-omi-heart=""
            className="omi-heart pointer-events-none absolute left-[42%] top-[16%] text-brand-400"
            style={{
              // @ts-expect-error CSS 自定义属性
              '--hx': `${h.dx}px`,
              '--hr': `${h.rot}deg`,
              animationDelay: `${h.delay}ms`,
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 21s-7.5-4.6-9.3-9.2C1.3 8.2 3.4 5 6.8 5c2 0 3.5 1.1 4.4 2.5.2.3.6.3.8 0C12.9 6.1 14.4 5 16.4 5c3.4 0 5.5 3.2 4.1 6.8C19 16.4 12 21 12 21z" />
            </svg>
          </span>
        ))}
      </div>
    </div>
  )
}

/** 四角星（点击瞬间的星星眼，与 Omi.tsx 的 Star 同形） */
function StarEye({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const w = r * 0.2
  return (
    <path
      d={`M${cx} ${cy - r} Q${cx + w} ${cy - w} ${cx + r} ${cy} Q${cx + w} ${cy + w} ${cx} ${cy + r} Q${cx - w} ${cy + w} ${cx - r} ${cy} Q${cx - w} ${cy - w} ${cx} ${cy - r} Z`}
      fill="#FFFFFF"
    />
  )
}
