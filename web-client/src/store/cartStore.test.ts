import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import type { CartItem, CartResponse } from '@/api/types'
import { useAuthStore } from './authStore'
import { useCartStore } from './cartStore'

const item: CartItem = {
  cart_item_id: 'cart-1',
  user_id: 'guest-1',
  product_id: 'product-1',
  sku_id: null,
  sku_label: '',
  title: 'Test product',
  brand: 'OmniCart',
  price: 99,
  image_url: '',
  quantity: 1,
  selected: true,
}

beforeEach(() => {
  vi.restoreAllMocks()
  useAuthStore.setState({ guestId: 'guest-1', userId: '', initialized: true })
  useCartStore.getState().reset()
})

describe('cart store loading', () => {
  it('deduplicates concurrent initial loads', async () => {
    let resolveRequest!: (value: CartResponse) => void
    vi.spyOn(api, 'getCart').mockImplementation(() => new Promise((resolve) => {
      resolveRequest = resolve
    }))

    const first = useCartStore.getState().loadCart()
    const second = useCartStore.getState().loadCart()
    expect(api.getCart).toHaveBeenCalledTimes(1)
    expect(useCartStore.getState()).toMatchObject({ isLoading: true, hasLoaded: false })

    resolveRequest({ user_id: 'guest-1', items: [item], total_price: 99, total_count: 1 })
    await Promise.all([first, second])
    expect(useCartStore.getState()).toMatchObject({ isLoading: false, hasLoaded: true, items: [item] })
  })

  it('uses the add response without triggering a full cart reload', async () => {
    vi.spyOn(api, 'addToCart').mockResolvedValue(item)
    const loadSpy = vi.spyOn(api, 'getCart')

    await expect(useCartStore.getState().addToCart('product-1')).resolves.toBe(true)

    expect(loadSpy).not.toHaveBeenCalled()
    expect(useCartStore.getState()).toMatchObject({ hasLoaded: true, items: [item] })
  })

  it('serializes rapid quantity intents so the latest value wins on the server', async () => {
    useCartStore.setState({ items: [item], hasLoaded: true })
    const resolvers: Array<(value: CartItem) => void> = []
    const update = vi.spyOn(api, 'updateCartItem').mockImplementation(() => new Promise((resolve) => {
      resolvers.push(resolve)
    }))

    const first = useCartStore.getState().setQuantity(item.cart_item_id, 2)
    const second = useCartStore.getState().setQuantity(item.cart_item_id, 3)
    await Promise.resolve()
    await Promise.resolve()
    expect(useCartStore.getState().items[0].quantity).toBe(3)
    expect(update).toHaveBeenCalledTimes(1)

    resolvers[0]({ ...item, quantity: 2 })
    await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(2))
    resolvers[1]({ ...item, quantity: 3 })
    await Promise.all([first, second])

    expect(update.mock.calls.map((call) => call[1])).toEqual([{ quantity: 2 }, { quantity: 3 }])
    expect(useCartStore.getState()).toMatchObject({ pendingIds: [] })
  })

  it('restores only the failed removed item without overwriting concurrent edits', async () => {
    const secondItem = { ...item, cart_item_id: 'cart-2', product_id: 'product-2', title: 'Second' }
    useCartStore.setState({ items: [item, secondItem], hasLoaded: true })
    vi.spyOn(api, 'removeCartItem').mockRejectedValue(new Error('delete failed'))
    const removing = useCartStore.getState().removeItem(item.cart_item_id)
    useCartStore.setState((state) => ({
      items: state.items.map((current) => current.cart_item_id === secondItem.cart_item_id ? { ...current, quantity: 7 } : current),
    }))
    await removing
    expect(useCartStore.getState().items).toEqual([item, { ...secondItem, quantity: 7 }])
  })

  it('computes totals and updates cart context', () => {
    const other = { ...item, cart_item_id: 'cart-2', quantity: 2, price: 50, selected: false }
    useCartStore.setState({ items: [item, other] })
    expect(useCartStore.getState().selectedCount()).toBe(1)
    expect(useCartStore.getState().totalCount()).toBe(3)
    expect(useCartStore.getState().totalPrice()).toBe(99)
    expect(useCartStore.getState().allSelected()).toBe(false)
    useCartStore.getState().setContext('session', 'conversation')
    expect(useCartStore.getState()).toMatchObject({ sessionId: 'session', conversationId: 'conversation' })
  })

  it('surfaces load and add failures without replacing existing items', async () => {
    vi.spyOn(api, 'getCart').mockRejectedValue(new Error('load failed'))
    await useCartStore.getState().loadCart()
    expect(useCartStore.getState()).toMatchObject({ hasLoaded: true, isLoading: false, error: 'load failed' })

    useCartStore.setState({ items: [item], error: null })
    vi.spyOn(api, 'addToCart').mockRejectedValue(new Error('add failed'))
    await expect(useCartStore.getState().addToCart('x')).resolves.toBe(false)
    expect(useCartStore.getState()).toMatchObject({ items: [item], error: 'add failed' })
  })

  it('replaces an existing item with the add response', async () => {
    useCartStore.setState({ items: [item] })
    vi.spyOn(api, 'addToCart').mockResolvedValue({ ...item, quantity: 4 })
    await useCartStore.getState().addToCart(item.product_id)
    expect(useCartStore.getState().items).toEqual([{ ...item, quantity: 4 }])
  })

  it('optimistically toggles one item and rolls back only the current failed intent', async () => {
    useCartStore.setState({ items: [item] })
    const update = vi.spyOn(api, 'updateCartItem').mockResolvedValue({ ...item, selected: false })
    await useCartStore.getState().toggleItem(item.cart_item_id)
    expect(useCartStore.getState()).toMatchObject({ pendingIds: [], items: [{ ...item, selected: false }] })
    expect(update).toHaveBeenCalledWith(item.cart_item_id, { selected: false }, expect.any(Object))

    update.mockRejectedValueOnce(new Error('toggle failed'))
    await useCartStore.getState().toggleItem(item.cart_item_id)
    expect(useCartStore.getState()).toMatchObject({ pendingIds: [], items: [{ ...item, selected: false }], error: 'toggle failed' })
  })

  it('handles select-all success and precise rollback', async () => {
    const other = { ...item, cart_item_id: 'cart-2', selected: false }
    useCartStore.setState({ items: [item, other] })
    const select = vi.spyOn(api, 'selectAllCart').mockResolvedValue({ ok: true })
    await useCartStore.getState().toggleSelectAll()
    expect(useCartStore.getState().items.every((current) => current.selected)).toBe(true)
    expect(useCartStore.getState().isSelectAllPending).toBe(false)

    select.mockRejectedValueOnce(new Error('select failed'))
    await useCartStore.getState().toggleSelectAll()
    expect(useCartStore.getState().items.every((current) => current.selected)).toBe(true)
    expect(useCartStore.getState()).toMatchObject({ isSelectAllPending: false, error: 'select failed' })
  })

  it('clamps quantity, rolls back failure, and removes successfully', async () => {
    useCartStore.setState({ items: [item] })
    const update = vi.spyOn(api, 'updateCartItem').mockResolvedValue({ ...item, quantity: 99 })
    await useCartStore.getState().setQuantity(item.cart_item_id, 120)
    expect(update).toHaveBeenCalledWith(item.cart_item_id, { quantity: 99 }, expect.any(Object))
    expect(useCartStore.getState().items[0].quantity).toBe(99)

    update.mockRejectedValueOnce(new Error('quantity failed'))
    await useCartStore.getState().setQuantity(item.cart_item_id, 4)
    expect(useCartStore.getState()).toMatchObject({ items: [{ ...item, quantity: 99 }], error: 'quantity failed' })

    vi.spyOn(api, 'removeCartItem').mockResolvedValue({ ok: true })
    await useCartStore.getState().removeItem(item.cart_item_id)
    expect(useCartStore.getState()).toMatchObject({ items: [], pendingIds: [] })
  })

  it('checks out selected items and handles empty and failed checkout', async () => {
    expect(await useCartStore.getState().checkout()).toBeNull()
    useCartStore.setState({ items: [item] })
    const checkout = vi.spyOn(api, 'checkout').mockResolvedValue({
      order_id: 'order-1', user_id: 'guest-1', items: [item], total_price: 99,
      status: 'created', message: 'ok',
    })
    await expect(useCartStore.getState().checkout()).resolves.toBe('ok')
    expect(checkout).toHaveBeenCalledWith(expect.objectContaining({ item_ids: [item.cart_item_id] }))
    expect(useCartStore.getState()).toMatchObject({ items: [], checkoutMessage: 'ok' })
    useCartStore.getState().dismissCheckoutMessage()
    expect(useCartStore.getState().checkoutMessage).toBeNull()

    useCartStore.setState({ items: [item] })
    checkout.mockRejectedValueOnce(new Error('checkout failed'))
    await expect(useCartStore.getState().checkout()).resolves.toBeNull()
    expect(useCartStore.getState().error).toBe('checkout failed')
    useCartStore.getState().clearError()
    expect(useCartStore.getState().error).toBeNull()
  })
})
