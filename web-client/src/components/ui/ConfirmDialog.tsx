import { AlertTriangle } from 'lucide-react'
import { Modal } from './Modal'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  pending?: boolean
  onConfirm: () => void | Promise<void>
  onClose: () => void
}

export function ConfirmDialog({ open, title, description, confirmLabel = '确认删除', pending, onConfirm, onClose }: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={onClose} title={title} className="max-w-sm">
      <div className="p-5">
        <div className="flex gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-rose-500/10 text-rose-500"><AlertTriangle size={20} /></span>
          <p className="pt-1 text-sm leading-relaxed text-ink-muted">{description}</p>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose} disabled={pending}>取消</button>
          <button className="rounded-xl bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-700 disabled:opacity-50" onClick={() => void onConfirm()} disabled={pending}>{pending ? '处理中…' : confirmLabel}</button>
        </div>
      </div>
    </Modal>
  )
}
