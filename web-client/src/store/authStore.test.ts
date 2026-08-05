import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '@/api/client'

const newConversation = vi.fn()
const resetCart = vi.fn()
const loadCart = vi.fn().mockResolvedValue(undefined)
vi.mock('./chatStore', () => ({ useChatStore: { getState: () => ({ newConversation }) } }))
vi.mock('./cartStore', () => ({ useCartStore: { getState: () => ({ reset: resetCart, loadCart }) } }))

import { useAuthStore } from './authStore'

const user = { user_id: 'u1', username: 'omi', token: 'native-token', email: 'omi@example.com' }
const guest = { guest_id: 'guest_1', guest_token: 'signed', expires_at: 123 }

beforeEach(() => {
  vi.restoreAllMocks()
  newConversation.mockClear()
  resetCart.mockClear()
  loadCart.mockClear()
  loadCart.mockResolvedValue(undefined)
  useAuthStore.setState({
    token: '', userId: '', guestId: '', username: '', email: '', phone: '', initialized: false,
    isLoading: false, error: null,
  })
})

describe('auth store', () => {
  it('restores a Cookie session without persisting the bearer token', async () => {
    vi.spyOn(api, 'profile').mockResolvedValue(user)
    await useAuthStore.getState().initialize()
    expect(useAuthStore.getState()).toMatchObject({ userId: 'u1', username: 'omi', token: '', initialized: true })
    expect(useAuthStore.getState().isLoggedIn()).toBe(true)
    expect(useAuthStore.getState().effectiveUserId()).toBe('u1')
    await useAuthStore.getState().initialize()
    expect(api.profile).toHaveBeenCalledTimes(1)
  })

  it('creates a guest after 401 and exposes initialization failures', async () => {
    vi.spyOn(api, 'profile').mockRejectedValue(new ApiError(401, 'no session'))
    vi.spyOn(api, 'guest').mockResolvedValue(guest)
    await useAuthStore.getState().initialize()
    expect(useAuthStore.getState()).toMatchObject({ guestId: 'guest_1', userId: '', initialized: true })
    expect(useAuthStore.getState().effectiveUserId()).toBe('guest_1')

    useAuthStore.setState({ initialized: false })
    vi.mocked(api.profile).mockRejectedValue(new Error('offline'))
    vi.mocked(api.guest).mockRejectedValue(new Error('guest offline'))
    await useAuthStore.getState().initialize()
    expect(useAuthStore.getState()).toMatchObject({ initialized: true, error: 'guest offline' })
  })

  it('deduplicates concurrent identity initialization', async () => {
    let rejectProfile!: (reason: unknown) => void
    vi.spyOn(api, 'profile').mockImplementation(() => new Promise((_resolve, reject) => {
      rejectProfile = reject
    }))
    vi.spyOn(api, 'guest').mockResolvedValue(guest)

    const first = useAuthStore.getState().initialize()
    const second = useAuthStore.getState().initialize()
    expect(api.profile).toHaveBeenCalledTimes(1)

    rejectProfile(new ApiError(401, 'no session'))
    await Promise.all([first, second])
    expect(api.guest).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState()).toMatchObject({ guestId: 'guest_1', initialized: true })
  })

  it('validates login and resets scoped state on login/register', async () => {
    await expect(useAuthStore.getState().login('', '')).resolves.toBe(false)
    expect(useAuthStore.getState().error).toContain('用户名')
    vi.spyOn(api, 'login').mockResolvedValue(user)
    await expect(useAuthStore.getState().login(' omi ', '12345678')).resolves.toBe(true)
    expect(api.login).toHaveBeenCalledWith({ username: 'omi', password: '12345678' })
    expect(newConversation).toHaveBeenCalled()
    expect(resetCart).toHaveBeenCalled()
    expect(loadCart).toHaveBeenCalled()

    vi.spyOn(api, 'register').mockResolvedValue({ ...user, user_id: 'u2' })
    await expect(useAuthStore.getState().register(' new ', '12345678', ' e@x.com ', ' 138 ')).resolves.toBe(true)
    expect(api.register).toHaveBeenCalledWith({ username: 'new', password: '12345678', email: 'e@x.com', phone: '138' })
  })

  it('does not block a successful login on cart refresh', async () => {
    vi.spyOn(api, 'login').mockResolvedValue(user)
    loadCart.mockReturnValue(new Promise(() => {}))

    await expect(useAuthStore.getState().login('omi', '12345678')).resolves.toBe(true)
    expect(useAuthStore.getState()).toMatchObject({ userId: 'u1', isLoading: false })
  })

  it('handles authentication errors, logout and session expiry', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new Error('wrong password'))
    await expect(useAuthStore.getState().login('u', 'bad')).resolves.toBe(false)
    expect(useAuthStore.getState().error).toBe('wrong password')
    vi.spyOn(api, 'register').mockRejectedValue(new Error('duplicate'))
    await expect(useAuthStore.getState().register('u', '12345678')).resolves.toBe(false)
    expect(useAuthStore.getState().error).toBe('duplicate')

    useAuthStore.setState({ userId: 'u1', initialized: true })
    vi.spyOn(api, 'logout').mockResolvedValue({ ...guest, ok: true })
    await useAuthStore.getState().logout()
    expect(useAuthStore.getState()).toMatchObject({ userId: '', guestId: 'guest_1', initialized: true })
    useAuthStore.getState().expireSession()
    expect(useAuthStore.getState()).toMatchObject({ initialized: false, userId: '' })
    useAuthStore.getState().clearError()
    expect(useAuthStore.getState().error).toBeNull()

    useAuthStore.setState({ userId: 'u1', guestId: '', username: 'omi', initialized: true })
    vi.mocked(api.logout).mockRejectedValue(new Error('offline'))
    await expect(useAuthStore.getState().logout()).resolves.toBe(false)
    expect(useAuthStore.getState()).toMatchObject({ userId: 'u1', username: 'omi', guestId: '', error: 'offline' })
  })
})
