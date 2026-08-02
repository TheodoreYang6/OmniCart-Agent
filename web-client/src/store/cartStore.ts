/**
 * 购物车状态 — 对应安卓端 CartViewModel.kt。
 *
 * 采用乐观更新：先改本地 UI，再异步同步后端，失败时回滚并提示。
 * session/conversation 上下文用于后端行为记录。
 */
import { create } from 'zustand'
import { api } from '@/api/client'
import type { CartItem } from '@/api/types'
import { getEffectiveUserId } from './authStore'

interface CartState {
  items: CartItem[]
  isLoading: boolean
  error: string | null
  checkoutMessage: string | null
  sessionId: string
  conversationId: string

  selectedCount: () => number
  totalPrice: () => number
  totalCount: () => number
  allSelected: () => boolean

  setContext: (sessionId: string, conversationId: string) => void
  loadCart: () => Promise<void>
  addToCart: (productId: string, skuId?: string | null, quantity?: number) => Promise<boolean>
  toggleItem: (id: string) => Promise<void>
  toggleSelectAll: () => Promise<void>
  setQuantity: (id: string, quantity: number) => Promise<void>
  removeItem: (id: string) => Promise<void>
  checkout: () => Promise<string | null>
  dismissCheckoutMessage: () => void
  clearError: () => void
}

export const useCartStore = create<CartState>((set, get) => {
  const ctx = () => ({
    user_id: getEffectiveUserId(),
    session_id: get().sessionId,
    conversation_id: get().conversationId,
  })

  return {
    items: [],
    isLoading: false,
    error: null,
    checkoutMessage: null,
    sessionId: '',
    conversationId: '',

    selectedCount: () => get().items.filter((i) => i.selected).length,
    totalPrice: () =>
      get()
        .items.filter((i) => i.selected)
        .reduce((sum, i) => sum + i.price * i.quantity, 0),
    totalCount: () => get().items.reduce((sum, i) => sum + i.quantity, 0),
    allSelected: () => {
      const items = get().items
      return items.length > 0 && items.every((i) => i.selected)
    },

    setContext: (sessionId, conversationId) => set({ sessionId, conversationId }),

    loadCart: async () => {
      set({ isLoading: true, error: null })
      try {
        const res = await api.getCart(ctx())
        set({ isLoading: false, items: res.items ?? [] })
      } catch (e) {
        set({ isLoading: false, error: e instanceof Error ? e.message : '加载购物车失败' })
      }
    },

    addToCart: async (productId, skuId = null, quantity = 1) => {
      try {
        await api.addToCart({ product_id: productId, sku_id: skuId, quantity }, ctx())
        await get().loadCart()
        return true
      } catch (e) {
        set({ error: e instanceof Error ? e.message : '加购失败' })
        return false
      }
    },

    toggleItem: async (id) => {
      const target = get().items.find((i) => i.cart_item_id === id)
      if (!target) return
      const next = !target.selected
      set((s) => ({
        items: s.items.map((i) => (i.cart_item_id === id ? { ...i, selected: next } : i)),
      }))
      try {
        await api.updateCartItem(id, { selected: next }, ctx())
      } catch (e) {
        // 回滚
        set((s) => ({
          items: s.items.map((i) => (i.cart_item_id === id ? { ...i, selected: !next } : i)),
          error: e instanceof Error ? e.message : '操作失败',
        }))
      }
    },

    toggleSelectAll: async () => {
      const next = !get().allSelected()
      set((s) => ({ items: s.items.map((i) => ({ ...i, selected: next })) }))
      try {
        await api.selectAllCart(next, ctx())
      } catch (e) {
        set({ error: e instanceof Error ? e.message : '操作失败' })
        await get().loadCart()
      }
    },

    setQuantity: async (id, quantity) => {
      if (quantity < 1) return
      const prev = get().items.find((i) => i.cart_item_id === id)?.quantity ?? 1
      set((s) => ({
        items: s.items.map((i) => (i.cart_item_id === id ? { ...i, quantity } : i)),
      }))
      try {
        await api.updateCartItem(id, { quantity }, ctx())
      } catch (e) {
        set((s) => ({
          items: s.items.map((i) => (i.cart_item_id === id ? { ...i, quantity: prev } : i)),
          error: e instanceof Error ? e.message : '操作失败',
        }))
      }
    },

    removeItem: async (id) => {
      const snapshot = get().items
      set((s) => ({ items: s.items.filter((i) => i.cart_item_id !== id) }))
      try {
        await api.removeCartItem(id, ctx())
      } catch (e) {
        set({ items: snapshot, error: e instanceof Error ? e.message : '删除失败' })
      }
    },

    checkout: async () => {
      const selectedIds = get()
        .items.filter((i) => i.selected)
        .map((i) => i.cart_item_id)
      if (selectedIds.length === 0) return null
      try {
        const res = await api.checkout({
          user_id: getEffectiveUserId(),
          item_ids: selectedIds,
          session_id: get().sessionId,
          conversation_id: get().conversationId,
        })
        set((s) => ({
          items: s.items.filter((i) => !i.selected),
          checkoutMessage: res.message,
        }))
        return res.message
      } catch (e) {
        set({ error: e instanceof Error ? e.message : '结算失败' })
        return null
      }
    },

    dismissCheckoutMessage: () => set({ checkoutMessage: null }),
    clearError: () => set({ error: null }),
  }
})
