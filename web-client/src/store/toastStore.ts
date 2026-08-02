import { create } from 'zustand'

export type ToastKind = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  kind: ToastKind
  message: string
}

interface ToastState {
  toasts: Toast[]
  show: (message: string, kind?: ToastKind) => void
  dismiss: (id: string) => void
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  show: (message, kind = 'info') => {
    const id = Math.random().toString(36).slice(2, 10)
    set((s) => ({ toasts: [...s.toasts, { id, kind, message }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 2800)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

/** 便捷函数，可在非组件环境调用。 */
export const toast = {
  success: (m: string) => useToastStore.getState().show(m, 'success'),
  error: (m: string) => useToastStore.getState().show(m, 'error'),
  info: (m: string) => useToastStore.getState().show(m, 'info'),
}
