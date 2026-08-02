import { useState } from 'react'
import { Omi, OmiAvatar, type OmiExpression, type OmiPhase } from '@/components/brand/Omi'
import { XiaoO, XiaoOAvatar } from '@/components/brand/XiaoO'

/**
 * 品牌资产走查页（/brand）—— 设计评审用，不参与任何业务流程。
 *
 * 用途：在真实渲染环境下检视欧米的 9 表情、尺寸下限、动效相位，
 * 以及与小O 并置时的冷暖对比与规格一致性；确认后再决定铺到哪些业务位置。
 */

const EXPRESSIONS: { key: OmiExpression; label: string; scene: string }[] = [
  { key: 'happy', label: '开心笑', scene: '回答完成' },
  { key: 'star', label: '星星眼', scene: '发现高分好物' },
  { key: 'thinking', label: '思考中', scene: '检索 / 推理阶段' },
  { key: 'wink', label: '眨眼', scene: '加购 / 下单成功' },
  { key: 'sleepy', label: '打瞌睡', scene: '空闲态' },
  { key: 'search', label: '搜索中', scene: '深度思考多轮检索' },
  { key: 'surprised', label: '惊讶', scene: '零结果 / 无匹配' },
  { key: 'pleading', label: '撒娇', scene: '引导登录 / 补充需求' },
  { key: 'smug', label: '得意', scene: '订单完成' },
]

const SIZES = [24, 32, 48, 72, 120]
const PHASES: OmiPhase[] = ['idle', 'thinking', 'talking']

export function BrandPreviewPage() {
  const [exp, setExp] = useState<OmiExpression>('star')

  return (
    <div className="aurora-bg min-h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-extrabold text-ink">品牌资产走查</h1>
          <p className="text-sm text-ink-muted">
            欧米 Omi · 情绪型吉祥物（导购猫）—— 设计评审专用页，未接入业务流程
          </p>
        </header>

        {/* 3D 主视觉（位图）—— 与 SVG 组件分工 */}
        <section className="card space-y-4 p-6">
          <div className="space-y-1">
            <h2 className="text-base font-bold text-ink">3D 主视觉（位图资产）</h2>
            <p className="text-xs text-ink-muted">
              用于 KV / 欢迎页大图 / 空状态插画 / 宣传物料——冲击力优先；
              小尺寸头像与状态图标仍用下方 SVG 组件（可无损缩放、props 切表情）
            </p>
          </div>
          <div className="flex flex-wrap items-start gap-6">
            <div className="flex flex-col items-center gap-2">
              <img
                src="/brand/omi-hero.png"
                alt="欧米 3D 主形象"
                className="w-56 rounded-2xl bg-[var(--glass-bg)]"
              />
              <span className="text-xs text-ink-muted">主形象 · 举爪打招呼</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <img
                src="/brand/omi-poses.png"
                alt="欧米 3D 三态：打招呼 / 思考中 / 开心满足"
                className="w-[26rem] rounded-2xl bg-[var(--glass-bg)]"
              />
              <span className="text-xs text-ink-muted">姿态三态 · 打招呼 / 思考中 / 开心满足</span>
            </div>
          </div>
        </section>

        {/* 主形象 */}
        <section className="card space-y-4 p-6">
          <h2 className="text-base font-bold text-ink">SVG 组件（含身体）</h2>
          <div className="flex flex-wrap items-end gap-8">
            <div className="flex flex-col items-center gap-2">
              <Omi size={180} expression={exp} withBody float />
              <span className="text-xs text-ink-muted">withBody + float</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Omi size={180} expression={exp} withBody phase="thinking" />
              <span className="text-xs text-ink-muted">thinking（尾尖呼吸）</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {EXPRESSIONS.map((e) => (
              <button
                key={e.key}
                onClick={() => setExp(e.key)}
                className={exp === e.key ? 'chip bg-brand-500 text-white' : 'chip'}
              >
                {e.label}
              </button>
            ))}
          </div>
        </section>

        {/* 9 表情矩阵 */}
        <section className="card space-y-4 p-6">
          <h2 className="text-base font-bold text-ink">表情系统（9 态 · 映射产品状态）</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {EXPRESSIONS.map((e) => (
              <div
                key={e.key}
                className="flex flex-col items-center gap-1.5 rounded-2xl bg-[var(--glass-bg)] p-4"
              >
                <Omi size={84} expression={e.key} />
                <span className="text-xs font-semibold text-ink">{e.label}</span>
                <span className="text-[11px] text-ink-muted">{e.scene}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 尺寸下限 */}
        <section className="card space-y-4 p-6">
          <h2 className="text-base font-bold text-ink">尺寸可用性（24px 下限验证）</h2>
          <div className="flex flex-wrap items-end gap-6">
            {SIZES.map((s) => (
              <div key={s} className="flex flex-col items-center gap-1.5">
                <Omi size={s} expression="happy" />
                <span className="text-[11px] text-ink-muted">{s}px</span>
              </div>
            ))}
          </div>
        </section>

        {/* 头像容器 + 相位 */}
        <section className="card space-y-4 p-6">
          <h2 className="text-base font-bold text-ink">头像容器与相位动效</h2>
          <div className="flex flex-wrap items-center gap-8">
            {PHASES.map((p) => (
              <div key={p} className="flex flex-col items-center gap-2">
                <OmiAvatar size={44} phase={p} />
                <span className="text-[11px] text-ink-muted">phase={p}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 与小O 并置对比 */}
        <section className="card space-y-4 p-6">
          <h2 className="text-base font-bold text-ink">双吉祥物并置（冷暖对比 · 规格一致性）</h2>
          <div className="flex flex-wrap items-end gap-10">
            <div className="flex flex-col items-center gap-2">
              <XiaoO size={140} expression="happy" withBody />
              <span className="text-xs font-semibold text-ink">小O · 系统身份</span>
              <span className="text-[11px] text-ink-muted">冷调 · 纯白 + 科技蓝</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <Omi size={140} expression="star" withBody />
              <span className="text-xs font-semibold text-ink">欧米 · 情绪身份</span>
              <span className="text-[11px] text-ink-muted">暖调 · 奶油白 + 粉 + 同款蓝</span>
            </div>
          </div>
          <div className="flex items-center gap-6 rounded-2xl bg-[var(--glass-bg)] p-4">
            <div className="flex items-center gap-2">
              <XiaoOAvatar size={40} />
              <span className="text-xs text-ink-muted">XiaoOAvatar</span>
            </div>
            <div className="flex items-center gap-2">
              <OmiAvatar size={40} expression="star" />
              <span className="text-xs text-ink-muted">OmiAvatar（同规格可互换）</span>
            </div>
          </div>
        </section>

        {/* 色板 */}
        <section className="card space-y-4 p-6">
          <h2 className="text-base font-bold text-ink">欧米色板</h2>
          <div className="flex flex-wrap gap-3">
            {[
              ['#FDF6EC', '奶油白 · 主体'],
              ['#E8DFD3', '暖灰 · 描边'],
              ['#C3D6E8', '蓝灰 · 头顶虎斑'],
              ['#256BFF', '科技蓝 · 共享 DNA'],
              ['#7DD3FC', '浅蓝 · 渐变端'],
              ['#BFDCFF', 'omi 挂牌底色'],
              ['#A8CFF5', '爪垫蓝'],
              ['#FFC9CE', '樱花粉 · 腮红'],
              ['#FF9FAE', '蜜桃粉 · 鼻'],
            ].map(([hex, name]) => (
              <div key={hex} className="flex items-center gap-2 rounded-xl bg-[var(--glass-bg)] px-3 py-2">
                <span
                  className="h-7 w-7 shrink-0 rounded-lg border border-[var(--field-border)]"
                  style={{ background: hex }}
                />
                <div className="leading-tight">
                  <p className="font-mono text-[11px] text-ink">{hex}</p>
                  <p className="text-[10px] text-ink-muted">{name}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
