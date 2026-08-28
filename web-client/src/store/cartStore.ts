/**
 * 购物车状态 — 对应安卓端 CartViewModel.kt。
 *
 * 采用乐观更新：先改本地 UI，再异步同步后端，失败时回滚并提示。
 * session/conversation 上下文用于后端行为记录。
 */
import { create } from 'zustand'
import { api } from '@/api/client'
import type { CartItem, CheckoutPreviewResponse, CheckoutSubmitResponse } from '@/api/types'
import { getEffectiveUserId, useAuthStore } from './authStore'

interface CartState {
  items: CartItem[]
  isLoading: boolean
  hasLoaded: boolean
  error: string | null
  checkoutMessage: string | null
  sessionId: string
  conversationId: string
  pendingIds: string[]
  isSelectAllPending: boolean

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
  previewCheckout: () => Promise<CheckoutPreviewResponse | null>
  submitCheckout: () => Promise<CheckoutSubmitResponse | null>
  dismissCheckoutMessage: () => void
  clearError: () => void
  reset: () => void
}

const mutationVersions = new Map<string, number>()
const mutationChains = new Map<string, Promise<void>>()
let cartLoadPromise: Promise<void> | null = null
let cartLoadGeneration = 0
let selectAllVersion = 0
const beginMutation = (id: string) => {
  const version = (mutationVersions.get(id) ?? 0) + 1
  mutationVersions.set(id, version)
  return version
}
const isCurrentMutation = (id: string, version: number) => mutationVersions.get(id) === version
const enqueueItemMutation = (id: string, operation: () => Promise<unknown>): Promise<void> => {
  const previous = mutationChains.get(id) ?? Promise.resolve()
  const current = previous
    .catch(() => undefined)
    .then(async () => { await operation() })
    .finally(() => {
      if (mutationChains.get(id) === current) mutationChains.delete(id)
    })
  mutationChains.set(id, current)
  return current
}

export const useCartStore = create<CartState>((set, get) => {
  const ctx = () => ({
    user_id: getEffectiveUserId(),
    session_id: get().sessionId,
    conversation_id: get().conversationId,
  })
  const requireLogin = (action: string) => {
    if (useAuthStore.getState().isLoggedIn()) return true
    set({ error: `登录后即可${action}` })
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('omnicart:login-required', { detail: { action } }))
    }
    return false
  }

  return {
    items: [],
    isLoading: false,
    hasLoaded: false,
    error: null,
    checkoutMessage: null,
    sessionId: '',
    conversationId: '',
    pendingIds: [],
    isSelectAllPending: false,

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
      if (!requireLogin("查看购物车")) {
        set({ isLoading: false, hasLoaded: true, items: [] })
        return
      }
      if (cartLoadPromise) return cartLoadPromise

      const generation = cartLoadGeneration
      set({ isLoading: true, error: null })
      cartLoadPromise = (async () => {
        try {
          const res = await api.getCart(ctx())
          if (generation === cartLoadGeneration) {
            set({ isLoading: false, hasLoaded: true, items: res.items ?? [] })
          }
        } catch (e) {
          if (generation === cartLoadGeneration) {
            set({
              isLoading: false,
              hasLoaded: true,
              error: e instanceof Error ? e.message : '加载购物车失败',
            })
          }
        } finally {
          if (generation === cartLoadGeneration) cartLoadPromise = null
        }
      })()
      return cartLoadPromise
    },

    addToCart: async (productId, skuId = null, quantity = 1) => {
      if (!requireLogin("加入购物车")) return false
      try {
        const item = await api.addToCart({ product_id: productId, sku_id: skuId, quantity }, ctx())
        if (!item || typeof item.cart_item_id !== 'string' || !item.cart_item_id) {
          set({ error: '加购失败' })
          return false
        }
        set((state) => {
          const exists = state.items.some((current) => current.cart_item_id === item.cart_item_id)
          return {
            hasLoaded: true,
            items: exists
              ? state.items.map((current) => current.cart_item_id === item.cart_item_id ? item : current)
              : [...state.items, item],
          }
        })
        return true
      } catch (e) {
        set({ error: e instanceof Error ? e.message : '加购失败' })
        return false
      }
    },

    toggleItem: async (id) => {
      if (!requireLogin("管理购物车")) return
      const target = get().items.find((i) => i.cart_item_id === id)
      if (!target) return
      const next = !target.selected
      const version = beginMutation(id)
      set((s) => ({
        items: s.items.map((i) => (i.cart_item_id === id ? { ...i, selected: next } : i)),
        pendingIds: Array.from(new Set([...s.pendingIds, id])),
      }))
      try {
        await enqueueItemMutation(id, () => api.updateCartItem(id, { selected: next }, ctx()))
        if (isCurrentMutation(id, version)) {
          set((s) => ({ pendingIds: s.pendingIds.filter((itemId) => itemId !== id) }))
        }
      } catch (e) {
        if (isCurrentMutation(id, version)) {
          set((s) => ({
            items: s.items.map((i) => (i.cart_item_id === id ? { ...i, selected: target.selected } : i)),
            pendingIds: s.pendingIds.filter((itemId) => itemId !== id),
            error: e instanceof Error ? e.message : '操作失败',
          }))
        }
      }
    },

    toggleSelectAll: async () => {
      if (!requireLogin("管理购物车")) return
      const next = !get().allSelected()
      const version = ++selectAllVersion
      const previous = new Map(get().items.map((item) => [item.cart_item_id, item.selected]))
      set((s) => ({
        items: s.items.map((i) => ({ ...i, selected: next })),
        isSelectAllPending: true,
      }))
      try {
        await api.selectAllCart(next, ctx())
        if (selectAllVersion === version) set({ isSelectAllPending: false })
      } catch (e) {
        if (selectAllVersion === version) {
          set((state) => ({
            items: state.items.map((item) => (
              item.selected === next && previous.has(item.cart_item_id)
                ? { ...item, selected: previous.get(item.cart_item_id) ?? item.selected }
                : item
            )),
            isSelectAllPending: false,
            error: e instanceof Error ? e.message : '操作失败',
          }))
        }
      }
    },

    setQuantity: async (id, quantity) => {
      if (!requireLogin("管理购物车")) return
      quantity = Math.max(1, Math.min(99, quantity))
      const prev = get().items.find((i) => i.cart_item_id === id)?.quantity ?? 1
      const version = beginMutation(id)
      set((s) => ({
        items: s.items.map((i) => (i.cart_item_id === id ? { ...i, quantity } : i)),
        pendingIds: Array.from(new Set([...s.pendingIds, id])),
      }))
      try {
        await enqueueItemMutation(id, () => api.updateCartItem(id, { quantity }, ctx()))
        if (isCurrentMutation(id, version)) {
          set((s) => ({ pendingIds: s.pendingIds.filter((itemId) => itemId !== id) }))
        }
      } catch (e) {
        if (isCurrentMutation(id, version)) {
          set((s) => ({
            items: s.items.map((i) => (i.cart_item_id === id ? { ...i, quantity: prev } : i)),
            pendingIds: s.pendingIds.filter((itemId) => itemId !== id),
            error: e instanceof Error ? e.message : '操作失败',
          }))
        }
      }
    },

    removeItem: async (id) => {
      if (!requireLogin("管理购物车")) return
      const index = get().items.findIndex((item) => item.cart_item_id === id)
      const removed = get().items[index]
      if (!removed) return
      set((s) => ({
        items: s.items.filter((i) => i.cart_item_id !== id),
        pendingIds: Array.from(new Set([...s.pendingIds, id])),
      }))
      try {
        await enqueueItemMutation(id, () => api.removeCartItem(id, ctx()))
        set((state) => ({ pendingIds: state.pendingIds.filter((itemId) => itemId !== id) }))
      } catch (e) {
        set((state) => {
          if (state.items.some((item) => item.cart_item_id === id)) {
            return { pendingIds: state.pendingIds.filter((itemId) => itemId !== id), error: e instanceof Error ? e.message : '删除失败' }
          }
          const items = [...state.items]
          items.splice(Math.min(index, items.length), 0, removed)
          return { items, pendingIds: state.pendingIds.filter((itemId) => itemId !== id), error: e instanceof Error ? e.message : '删除失败' }
        })
      }
    },

    checkout: async () => {
      if (!requireLogin("结算")) return null
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

    previewCheckout: async () => {
      if (!requireLogin("结算")) return null
      const selectedIds = get()
        .items.filter((i) => i.selected)
        .map((i) => i.cart_item_id)
      if (selectedIds.length === 0) return null
      try {
        return await api.checkoutPreview({
          user_id: getEffectiveUserId(),
          item_ids: selectedIds,
          session_id: get().sessionId,
          conversation_id: get().conversationId,
        })
      } catch (e) {
        set({ error: e instanceof Error ? e.message : '获取结算信息失败' })
        return null
      }
    },

    submitCheckout: async () => {
      if (!requireLogin("结算")) return null
      const selectedIds = get()
        .items.filter((i) => i.selected)
        .map((i) => i.cart_item_id)
      if (selectedIds.length === 0) return null
      try {
        const res = await api.checkoutSubmit({
          user_id: getEffectiveUserId(),
          item_ids: selectedIds,
          session_id: get().sessionId,
          conversation_id: get().conversationId,
        })
        set((s) => ({
          items: s.items.filter((i) => !i.selected),
          checkoutMessage: res.answer || res.message,
        }))
        return res
      } catch (e) {
        set({ error: e instanceof Error ? e.message : '结算失败' })
        return null
      }
    },

    dismissCheckoutMessage: () => set({ checkoutMessage: null }),
    clearError: () => set({ error: null }),
    reset: () => {
      mutationVersions.clear()
      mutationChains.clear()
      selectAllVersion += 1
      cartLoadGeneration += 1
      cartLoadPromise = null
      set({ items: [], isLoading: false, hasLoaded: false, error: null, checkoutMessage: null, pendingIds: [], isSelectAllPending: false })
    },
  }
})
