import { useEffect, useRef, useState } from 'react'
import type { MascotPhase } from '@/store/chatStore'
import type { OmiExpression, OmiPhase } from '@/components/brand/Omi'

/**
 * 欧米动效映射 —— 把产品状态统一翻译成 (expression, phase) 二元组。
 *
 * 设计原则（用户要求：不夸张、与现有 UI 协调）：
 *  - 只复用组件已有的 expression / phase 两个属性，不引入新动画词汇
 *  - 常态一律 idle + happy；只有真实状态变化才动，避免"一直在跳"的廉价感
 *  - 瞬时反馈（加购/下单成功）自动在 1.6s 后回落常态，不长期占用视觉
 *
 * 三大场景：
 *  ① 查询商品：searching → 搜索中（放大镜）/ analyzing → 思考中（头顶三点）
 *                流式吐字 → talking 轻弹跳 + 开心笑
 *  ② 浏览卡片：打开 Spotlight → 星星眼（发现好物）；高分商品加成
 *  ③ 下单过程：加购成功 → 眨眼；下单完成 → 得意
 */

/** 瞬时反馈事件（由业务侧触发，自动回落） */
export type OmiFeedback = 'added-to-cart' | 'order-placed' | 'found-good' | null

interface OmiStateInput {
  /** 会话相位（chatStore.phase） */
  phase: MascotPhase
  /** 是否流式进行中 */
  isStreaming: boolean
  /** 是否已有流式文字（区分"思考中"与"正在说"） */
  hasStreamingText: boolean
}

export interface OmiVisualState {
  expression: OmiExpression
  phase: OmiPhase
}

/** 瞬时反馈 → 视觉态 */
const FEEDBACK_MAP: Record<Exclude<OmiFeedback, null>, OmiVisualState> = {
  'added-to-cart': { expression: 'wink', phase: 'talking' },
  'order-placed': { expression: 'smug', phase: 'talking' },
  'found-good': { expression: 'star', phase: 'talking' },
}

const FEEDBACK_MS = 1600

/**
 * 欧米视觉状态钩子。
 *
 * @example
 * const { visual, fire } = useOmiState({ phase, isStreaming, hasStreamingText })
 * <OmiAvatar {...visual} />
 * fire('added-to-cart')   // 加购成功时触发瞬时反馈
 */
export function useOmiState(input: OmiStateInput) {
  const { phase, isStreaming, hasStreamingText } = input
  const [feedback, setFeedback] = useState<OmiFeedback>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fire = (f: Exclude<OmiFeedback, null>) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setFeedback(f)
    timerRef.current = setTimeout(() => setFeedback(null), FEEDBACK_MS)
  }

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  // 优先级：瞬时反馈 > 会话状态 > 常态
  let visual: OmiVisualState
  if (feedback) {
    visual = FEEDBACK_MAP[feedback]
  } else if (isStreaming) {
    if (hasStreamingText) {
      // 正在吐字 → 轻弹跳 + 开心
      visual = { expression: 'happy', phase: 'talking' }
    } else if (phase === 'searching') {
      // 检索中 → 放大镜 + 光环呼吸
      visual = { expression: 'search', phase: 'thinking' }
    } else {
      // 分析/规划中 → 头顶三点 + 光环呼吸
      visual = { expression: 'thinking', phase: 'thinking' }
    }
  } else {
    visual = { expression: 'happy', phase: 'idle' }
  }

  return { visual, fire, feedback }
}

/** 商品评分 → 卡片场景表情（Spotlight 打开时用；≥9.2 才给星星眼，避免滥用） */
export function omiExpressionForScore(displayScore?: number): OmiExpression {
  if (typeof displayScore !== 'number') return 'happy'
  if (displayScore >= 9.2) return 'star'
  if (displayScore >= 8.5) return 'happy'
  return 'thinking'
}
