import type { AddressCreateRequest } from '@/api/types'

interface AddressFormProps {
  value: AddressCreateRequest
  onChange: (value: AddressCreateRequest) => void
  saving: boolean
  onSubmit: () => void
  submitLabel?: string
}

/** 收货地址表单（新增/编辑共用）。字段标签与辅助信息统一，避免只靠占位文字输入。 */
export function AddressForm({ value, onChange, saving, onSubmit, submitLabel = '保存地址' }: AddressFormProps) {
  const set = (patch: Partial<AddressCreateRequest>) => onChange({ ...value, ...patch })
  const labelClass = 'mb-1.5 block text-xs font-medium text-ink-soft'

  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit() }}>
      <p className="rounded-xl bg-[var(--surface-variant)] px-3 py-2.5 text-xs leading-relaxed text-ink-muted">请填写可准确收货的信息。欧米只会在本次订单配送中使用它。</p>
      <div className="grid grid-cols-2 gap-3">
        <label><span className={labelClass}>收货人</span><input className="input-field" autoComplete="name" placeholder="例如：王小明" value={value.name} onChange={(e) => set({ name: e.target.value })} /></label>
        <label><span className={labelClass}>手机号</span><input className="input-field" type="tel" inputMode="numeric" autoComplete="tel" placeholder="用于配送联系" value={value.phone} onChange={(e) => set({ phone: e.target.value })} /></label>
      </div>
      <div>
        <span className={labelClass}>所在地区</span>
        <div className="grid grid-cols-3 gap-2">
          <input className="input-field" placeholder="省" value={value.province ?? ''} onChange={(e) => set({ province: e.target.value })} />
          <input className="input-field" placeholder="市" value={value.city ?? ''} onChange={(e) => set({ city: e.target.value })} />
          <input className="input-field" placeholder="区 / 县" value={value.district ?? ''} onChange={(e) => set({ district: e.target.value })} />
        </div>
      </div>
      <label><span className={labelClass}>详细地址</span><textarea className="input-field min-h-[92px] resize-none" autoComplete="street-address" placeholder="街道、楼栋、单元、门牌号等" value={value.detail ?? ''} onChange={(e) => set({ detail: e.target.value })} /></label>
      <label className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-[var(--line)] px-3 py-2.5 text-sm text-ink-soft transition hover:bg-[var(--surface-variant)]">
        <input type="checkbox" checked={value.is_default ?? false} onChange={(e) => set({ is_default: e.target.checked })} className="h-4 w-4 accent-brand-500" />
        设为默认地址
      </label>
      <button type="submit" disabled={saving} className="btn-primary w-full py-3">{saving ? '保存中…' : submitLabel}</button>
    </form>
  )
}
