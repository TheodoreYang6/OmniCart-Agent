import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Sparkles, Trash2, Plus, Tag, Wallet } from 'lucide-react'
import { api } from '@/api/client'
import type { PreferenceEntry } from '@/api/types'
import { LoadingBlock, Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Omi } from '@/components/brand/Omi'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toastStore'
import { AGENT_NAME } from '@/config'
import { categoryIcon } from '@/lib/format'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  '我喜欢苹果和索尼，预算 3000 以内的数码产品',
  '敏感肌，护肤品避开酒精和香精',
  '常跑步，运动鞋要透气缓震',
]

export function PreferencePage() {
  const navigate = useNavigate()
  const effectiveUserId = useAuthStore((s) => s.userId || s.guestId)

  const [entries, setEntries] = useState<PreferenceEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<PreferenceEntry | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.getPreferenceEntries(effectiveUserId)
      setEntries(res.entries ?? [])
    } catch {
      toast.error('加载偏好失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveUserId])

  const save = async () => {
    const raw = text.trim()
    if (!raw) return
    setSaving(true)
    try {
      const res = await api.savePreferenceEntry(effectiveUserId, raw)
      if (res.ok && res.entry) {
        toast.success('已记住你的偏好')
        setText('')
        await load()
      } else {
        toast.error(res.error || '解析失败，请描述更具体的品类')
      }
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const toggle = async (entry: PreferenceEntry) => {
    const next = !entry.enabled
    setEntries((prev) =>
      prev.map((e) => (e.entry_id === entry.entry_id ? { ...e, enabled: next } : e)),
    )
    try {
      await api.togglePreferenceEntry(entry.entry_id, effectiveUserId, next)
    } catch {
      setEntries((prev) =>
        prev.map((e) => (e.entry_id === entry.entry_id ? { ...e, enabled: !next } : e)),
      )
      toast.error('操作失败')
    }
  }

  const remove = async (entry: PreferenceEntry) => {
    setDeleting(true)
    setEntries((prev) => prev.filter((e) => e.entry_id !== entry.entry_id))
    try {
      await api.deletePreferenceEntry(entry.entry_id, effectiveUserId)
      setDeleteTarget(null)
    } catch {
      toast.error('删除失败')
      load()
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="aurora-bg flex h-full flex-col">
      <header className="glass-strong z-10 flex items-center gap-2 border-b border-[var(--line)] px-3 py-3">
        <button
          onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/profile')}
          className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-soft transition hover:bg-[var(--surface-variant)]"
          aria-label="返回"
        >
          <ArrowLeft size={20} />
        </button>
        <span className="font-medium text-ink">偏好设置</span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
          {/* Hero 区：把说明从输入框里解放出来，与开屏页同一套渐变标题语言 */}
          <div className="text-center">
            <h1 className="text-xl font-extrabold text-ink sm:text-2xl">
              让<span className="gradient-text">{AGENT_NAME}</span>更懂你
            </h1>
            <p className="mt-1.5 text-[13px] text-ink-muted">
              用一句自然语言描述长期偏好，每次推荐都会自动参考
            </p>
          </div>

          {/* 输入卡：玻璃大卡 + 聊天输入条同款 border-beam 聚焦流光 */}
          <div className="glass-strong mt-5 rounded-2xl p-4 sm:p-5">
            <div className="border-beam rounded-2xl bg-[var(--field-bg)] px-3.5 py-2.5 transition focus-within:bg-[var(--glass-bg-strong)]">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="例如：我喜欢苹果，预算 3000 以内的数码产品"
                className="min-h-[76px] w-full resize-none bg-transparent py-1 text-sm leading-relaxed text-ink outline-none placeholder:text-ink-muted"
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => setText(ex)}
                  className="group flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-transparent px-3 py-1.5 text-xs text-ink-soft transition hover:border-brand-300 hover:bg-brand-500/10 hover:text-brand-600"
                >
                  <Sparkles size={12} className="text-brand-400 transition-transform duration-200 group-hover:scale-125 group-hover:rotate-12" />
                  {ex}
                </button>
              ))}
            </div>
            <button
              onClick={save}
              disabled={saving || !text.trim()}
              className="btn-primary mt-4 w-full py-2.5"
            >
              {saving ? <Spinner size={18} className="text-white" /> : <Plus size={18} />}
              解析并记住
            </button>
          </div>

          {/* 已保存的偏好 */}
          <div className="mb-2.5 mt-7 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">已记住的偏好</h2>
            {entries.length > 0 && (
              <span className="rounded-full bg-brand-500/10 px-2 py-0.5 text-[11px] font-medium text-brand-600 dark:text-brand-300">
                {entries.length} 条
              </span>
            )}
          </div>
          {loading ? (
            <LoadingBlock text="加载中…" />
          ) : entries.length === 0 ? (
            <div className="glass flex flex-col items-center rounded-2xl px-6 py-10 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-500/10 ring-1 ring-brand-500/15">
                <Omi size={52} />
              </div>
              <p className="mt-3 text-sm font-semibold text-ink">还没有偏好记录</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                在上方告诉{AGENT_NAME}你的口味、预算和忌讳
                <br />
                推荐会越来越贴合你
              </p>
            </div>
          ) : (
            <div className="grid items-start gap-3 lg:grid-cols-2">
              {entries.map((e) => (
                <div key={e.entry_id} className="glass rounded-2xl p-4 transition">
                  <div className="flex items-start justify-between gap-3">
                    <div
                      className={cn(
                        'flex min-w-0 items-center gap-3 transition',
                        !e.enabled && 'opacity-55 saturate-50',
                      )}
                    >
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500/10 text-lg ring-1 ring-brand-500/15">
                        {categoryIcon(e.category)}
                      </span>
                      <div className="min-w-0">
                        <p className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                          <span className="truncate">
                            {e.category || '通用'}
                            {e.sub_category && ` · ${e.sub_category}`}
                          </span>
                          {!e.enabled && (
                            <span className="shrink-0 rounded-full bg-[var(--surface-variant)] px-1.5 py-0.5 text-[10px] font-normal text-ink-muted">
                              已停用
                            </span>
                          )}
                        </p>
                        <p className="line-clamp-1 text-xs text-ink-muted">{e.raw_text}</p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <Toggle on={e.enabled} onClick={() => toggle(e)} />
                      <button
                        onClick={() => setDeleteTarget(e)}
                        className="rounded-lg p-1.5 text-ink-muted transition hover:bg-rose-500/10 hover:text-rose-500"
                        aria-label={`删除偏好：${e.raw_text}`}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* 结构化标签 */}
                  <div
                    className={cn(
                      'mt-3 flex flex-wrap gap-1.5 transition',
                      !e.enabled && 'opacity-55 saturate-50',
                    )}
                  >
                    {e.brands?.map((b) => (
                      <Chip key={b} icon={<Tag size={11} />} text={b} />
                    ))}
                    {e.scenarios?.map((s) => (
                      <Chip key={s} text={s} />
                    ))}
                    {(e.budget_min || e.budget_max) && (
                      <Chip
                        icon={<Wallet size={11} />}
                        text={`¥${e.budget_min ?? 0} - ${e.budget_max ?? '∞'}`}
                      />
                    )}
                    {e.must_tags?.map((t) => (
                      <Chip key={t} text={`要${t}`} tone="good" />
                    ))}
                    {e.avoid_tags?.map((t) => (
                      <Chip key={t} text={`避${t}`} tone="bad" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      <ConfirmDialog open={!!deleteTarget} title="删除购物偏好" description={`确定删除“${deleteTarget?.raw_text ?? ''}”吗？欧米之后将不再参考这条信息。`} pending={deleting} onClose={() => setDeleteTarget(null)} onConfirm={async () => { if (deleteTarget) await remove(deleteTarget) }} />
    </div>
  )
}

function Chip({
  text,
  icon,
  tone = 'default',
}: {
  text: string
  icon?: React.ReactNode
  tone?: 'default' | 'good' | 'bad'
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]',
        // 双主题安全：半透底 + 深色下提亮文字，不用硬编码浅色块
        tone === 'good' && 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
        tone === 'bad' && 'bg-rose-500/10 text-rose-500 dark:text-rose-400',
        tone === 'default' && 'bg-[var(--surface-variant)] text-ink-muted',
      )}
    >
      {icon}
      {text}
    </span>
  )
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      role="switch"
      aria-checked={on}
      aria-label={on ? '停用偏好' : '启用偏好'}
      className={cn(
        'relative h-6 w-11 rounded-full transition',
        on ? 'gradient-brand shadow-glow' : 'bg-[var(--field-border)]',
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all',
          on ? 'left-[22px]' : 'left-0.5',
        )}
      />
    </button>
  )
}
