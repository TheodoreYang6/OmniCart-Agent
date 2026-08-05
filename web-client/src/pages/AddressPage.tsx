import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, MapPin, Pencil, Plus, Trash2, Check } from 'lucide-react'
import { api } from '@/api/client'
import type { Address, AddressCreateRequest } from '@/api/types'
import { Modal } from '@/components/ui/Modal'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingBlock } from '@/components/ui/Spinner'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toastStore'

const EMPTY_FORM: AddressCreateRequest = {
  name: '',
  phone: '',
  province: '',
  city: '',
  district: '',
  detail: '',
  is_default: false,
}

export function AddressPage() {
  const navigate = useNavigate()
  const effectiveUserId = useAuthStore((s) => s.userId || s.guestId)

  const [list, setList] = useState<Address[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<Address | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<AddressCreateRequest>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Address | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.getAddresses(effectiveUserId)
      setList(res.addresses ?? [])
    } catch {
      toast.error('加载地址失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveUserId])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  const openEdit = (a: Address) => {
    setEditing(a)
    setForm({
      name: a.name,
      phone: a.phone,
      province: a.province,
      city: a.city,
      district: a.district,
      detail: a.detail,
      is_default: a.is_default,
    })
    setShowForm(true)
  }

  const save = async () => {
    if (!form.name.trim() || !form.phone.trim()) {
      toast.error('请填写收货人和手机号')
      return
    }
    if (!form.detail?.trim()) {
      toast.error('请填写详细地址')
      return
    }
    setSaving(true)
    try {
      if (editing) {
        await api.updateAddress(editing.address_id, form, effectiveUserId)
        toast.success('地址已更新')
      } else {
        await api.createAddress(form, effectiveUserId)
        toast.success('地址已添加')
      }
      setShowForm(false)
      await load()
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (a: Address) => {
    setDeleting(true)
    try {
      await api.deleteAddress(a.address_id, effectiveUserId)
      setList((prev) => prev.filter((x) => x.address_id !== a.address_id))
      toast.success('已删除')
      setDeleteTarget(null)
    } catch {
      toast.error('删除失败')
    } finally {
      setDeleting(false)
    }
  }

  const setDefault = async (a: Address) => {
    try {
      await api.updateAddress(a.address_id, { is_default: true }, effectiveUserId)
      await load()
    } catch {
      toast.error('操作失败')
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
        <span className="flex-1 font-medium text-ink">收货地址</span>
        <button onClick={openCreate} className="btn-primary px-3 py-1.5 text-sm">
          <Plus size={16} /> 新增
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-4 py-5 sm:px-6">
          {loading ? (
            <LoadingBlock text="加载地址…" />
          ) : list.length === 0 ? (
            <EmptyState
              icon={<MapPin size={26} />}
              title="还没有收货地址"
              description="添加地址后，下单更便捷"
              action={
                <button onClick={openCreate} className="btn-primary mt-2">
                  <Plus size={18} /> 添加地址
                </button>
              }
            />
          ) : (
            <div className="grid items-start gap-3 lg:grid-cols-2">
              {list.map((a) => (
                <div
                  key={a.address_id}
                  className="glass card-hover p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-ink">{a.name}</span>
                        <span className="text-sm text-ink-muted">{a.phone}</span>
                        {a.is_default && (
                          <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
                            默认
                          </span>
                        )}
                      </div>
                      <p className="mt-1 text-sm leading-relaxed text-ink-soft">
                        {a.province}
                        {a.city}
                        {a.district} {a.detail}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <button
                        onClick={() => openEdit(a)}
                        className="rounded-lg p-1.5 text-ink-muted transition hover:bg-[var(--surface-variant)] hover:text-brand-500"
                        aria-label={`编辑 ${a.name} 的地址`}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(a)}
                        className="rounded-lg p-1.5 text-ink-muted transition hover:bg-rose-500/10 hover:text-rose-500"
                        aria-label={`删除 ${a.name} 的地址`}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                  {!a.is_default && (
                    <button
                      onClick={() => setDefault(a)}
                      className="mt-2 flex items-center gap-1 text-xs text-ink-muted transition hover:text-brand-500"
                    >
                      <Check size={13} /> 设为默认
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 表单 */}
      <Modal
        open={showForm}
        onClose={() => setShowForm(false)}
        title={editing ? '编辑地址' : '新增地址'}
        variant="bottom"
      >
        <div className="space-y-3 p-5">
          <div className="grid grid-cols-2 gap-3">
            <input
              className="input-field"
              placeholder="收货人"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="input-field"
              placeholder="手机号"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <input
              className="input-field"
              placeholder="省"
              value={form.province}
              onChange={(e) => setForm({ ...form, province: e.target.value })}
            />
            <input
              className="input-field"
              placeholder="市"
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
            />
            <input
              className="input-field"
              placeholder="区/县"
              value={form.district}
              onChange={(e) => setForm({ ...form, district: e.target.value })}
            />
          </div>
          <textarea
            className="input-field min-h-[72px] resize-none"
            placeholder="详细地址（街道、门牌号等）"
            value={form.detail}
            onChange={(e) => setForm({ ...form, detail: e.target.value })}
          />
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              className="h-4 w-4 accent-brand-500"
            />
            设为默认地址
          </label>
          <button onClick={save} disabled={saving} className="btn-primary w-full py-3">
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </Modal>
      <ConfirmDialog
        open={!!deleteTarget}
        title="删除收货地址"
        description={`确定删除“${deleteTarget?.name ?? ''}”的地址吗？此操作无法撤销。`}
        pending={deleting}
        onClose={() => setDeleteTarget(null)}
        onConfirm={async () => { if (deleteTarget) await remove(deleteTarget) }}
      />
    </div>
  )
}
