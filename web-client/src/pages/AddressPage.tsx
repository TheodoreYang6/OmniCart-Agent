import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, House, MapPin, Pencil, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import type { Address, AddressCreateRequest } from '@/api/types'
import { Modal } from '@/components/ui/Modal'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { LoadingBlock } from '@/components/ui/Spinner'
import { AddressForm } from '@/components/address/AddressForm'
import { useAuthStore } from '@/store/authStore'
import { toast } from '@/store/toastStore'

const EMPTY_FORM: AddressCreateRequest = { name: '', phone: '', province: '', city: '', district: '', detail: '', is_default: false }

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
    try { setList((await api.getAddresses(effectiveUserId)).addresses ?? []) } catch { toast.error('加载地址失败，请稍后重试') } finally { setLoading(false) }
  }
  useEffect(() => { void load() // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveUserId])

  const openCreate = () => { setEditing(null); setForm(EMPTY_FORM); setShowForm(true) }
  const openEdit = (address: Address) => {
    setEditing(address)
    setForm({ name: address.name, phone: address.phone, province: address.province, city: address.city, district: address.district, detail: address.detail, is_default: address.is_default })
    setShowForm(true)
  }
  const save = async () => {
    if (!form.name.trim() || !form.phone.trim()) { toast.error('请填写收货人和手机号'); return }
    if (![form.province, form.city, form.district, form.detail].every((item) => item?.trim())) { toast.error('请补全所在地区和详细地址'); return }
    setSaving(true)
    try {
      if (editing) { await api.updateAddress(editing.address_id, form, effectiveUserId); toast.success('地址已更新') } else { await api.createAddress(form, effectiveUserId); toast.success('地址已添加') }
      setShowForm(false); await load()
    } catch { toast.error('保存失败，请稍后重试') } finally { setSaving(false) }
  }
  const remove = async (address: Address) => {
    setDeleting(true)
    try { await api.deleteAddress(address.address_id, effectiveUserId); setList((previous) => previous.filter((item) => item.address_id !== address.address_id)); toast.success('地址已删除'); setDeleteTarget(null) } catch { toast.error('删除失败，请稍后重试') } finally { setDeleting(false) }
  }
  const setDefault = async (address: Address) => {
    try { await api.updateAddress(address.address_id, { is_default: true }, effectiveUserId); await load(); toast.success('已设为默认地址') } catch { toast.error('操作失败，请稍后重试') }
  }

  return (
    <div className="aurora-bg flex h-full flex-col">
      <header className="glass-strong z-10 flex items-center gap-2 border-b border-[var(--line)] px-3 py-3">
        <button onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/profile')} className="flex h-9 w-9 items-center justify-center rounded-xl text-ink-soft transition hover:bg-[var(--surface-variant)]" aria-label="返回"><ArrowLeft size={20} /></button>
        <span className="flex-1 font-semibold text-ink">收货地址</span>
        <button onClick={openCreate} className="btn-primary px-3 py-1.5 text-sm"><Plus size={16} /> 新增地址</button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:py-8">
          <section className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand-500">Delivery address</p><h1 className="mt-1 text-2xl font-bold tracking-tight text-ink">把心仪好物送到你手上</h1><p className="mt-1 text-sm text-ink-muted">默认地址会在结算时优先使用，可随时修改。</p></div>
            {!loading && list.length > 0 && <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-sm text-ink-soft"><MapPin size={15} className="text-brand-500" />已保存 {list.length} 个地址</span>}
          </section>

          {loading ? <LoadingBlock text="正在加载你的地址…" /> : list.length === 0 ? (
            <EmptyState icon={<MapPin size={28} />} title="还没有收货地址" description="提前添加一个地址，选好商品就能更快下单。" action={<button onClick={openCreate} className="btn-primary mt-2"><Plus size={18} /> 添加地址</button>} />
          ) : (
            <div className="grid items-start gap-4 lg:grid-cols-2">
              {list.map((address) => (
                <article key={address.address_id} className="glass group relative overflow-hidden border border-[var(--card-border)] p-5 shadow-lift transition hover:-translate-y-0.5 hover:shadow-float">
                  {address.is_default && <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-brand-500 to-sky-400" />}
                  <div className="flex gap-3">
                    <span className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${address.is_default ? 'bg-brand-500 text-white shadow-glow' : 'bg-[var(--surface-variant)] text-brand-500'}`}><House size={19} /></span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1"><strong className="text-base text-ink">{address.name}</strong><span className="text-sm text-ink-muted">{address.phone}</span>{address.is_default && <span className="rounded-full bg-brand-500/10 px-2 py-0.5 text-[11px] font-semibold text-brand-600 dark:text-brand-300">默认地址</span>}</div>
                      <p className="mt-2 text-sm leading-6 text-ink-soft">{address.province} {address.city} {address.district}<br />{address.detail}</p>
                    </div>
                  </div>
                  <div className="mt-5 flex items-center justify-between border-t border-[var(--line)] pt-3.5">
                    {address.is_default ? <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-300"><ShieldCheck size={15} />结算时优先使用</span> : <button onClick={() => setDefault(address)} className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-600 transition hover:text-brand-500"><Check size={15} />设为默认地址</button>}
                    <div className="flex items-center gap-1"><button onClick={() => openEdit(address)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium text-ink-soft transition hover:bg-[var(--surface-variant)] hover:text-brand-600"><Pencil size={14} />编辑</button><button onClick={() => setDeleteTarget(address)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium text-ink-muted transition hover:bg-rose-500/10 hover:text-rose-500"><Trash2 size={14} />删除</button></div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </main>
      </div>

      <Modal open={showForm} onClose={() => setShowForm(false)} title={editing ? '编辑收货地址' : '新增收货地址'} variant="bottom"><div className="p-5"><AddressForm value={form} onChange={setForm} saving={saving} onSubmit={save} submitLabel={editing ? '保存修改' : '保存地址'} /></div></Modal>
      <ConfirmDialog open={!!deleteTarget} title="删除收货地址" description={`确定删除“${deleteTarget?.name ?? ''}”的地址吗？此操作无法撤销。`} pending={deleting} onClose={() => setDeleteTarget(null)} onConfirm={async () => { if (deleteTarget) await remove(deleteTarget) }} />
    </div>
  )
}
