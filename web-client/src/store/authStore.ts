import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api, ApiError } from '@/api/client'
import type { AuthResponse } from '@/api/types'

interface AuthState {
  token: string
  userId: string
  guestId: string
  username: string
  email: string
  phone: string
  initialized: boolean
  isLoading: boolean
  error: string | null

  isLoggedIn: () => boolean
  effectiveUserId: () => string
  initialize: () => Promise<void>
  login: (username: string, password: string) => Promise<boolean>
  register: (username: string, password: string, email?: string, phone?: string) => Promise<boolean>
  logout: () => Promise<boolean>
  expireSession: () => void
  clearError: () => void
}

async function resetUserScopedState(loadCart = true) {
  const [{ useChatStore }, { useCartStore }] = await Promise.all([
    import('./chatStore'),
    import('./cartStore'),
  ])
  useChatStore.getState().newConversation()
  useCartStore.getState().reset()
  if (loadCart) void useCartStore.getState().loadCart()
}

let initializationPromise: Promise<void> | null = null
let identityGeneration = 0

const userFields = (res: AuthResponse) => ({
  token: '', // Web relies on the HttpOnly cookie; Bearer remains available to native clients.
  userId: res.user_id,
  guestId: '',
  username: res.username,
  email: res.email ?? '',
  phone: res.phone ?? '',
})

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: '',
      userId: '',
      guestId: '',
      username: '',
      email: '',
      phone: '',
      initialized: false,
      isLoading: false,
      error: null,

      isLoggedIn: () => Boolean(get().userId),
      effectiveUserId: () => get().userId || get().guestId,

      initialize: async () => {
        if (get().initialized) return
        if (initializationPromise) return initializationPromise

        const generation = identityGeneration
        set({ isLoading: true })
        initializationPromise = (async () => {
          try {
            const profile = await api.profile()
            if (generation === identityGeneration) {
              set({ ...userFields(profile), initialized: true, isLoading: false, error: null })
            }
          } catch (error) {
            if (generation !== identityGeneration) return
            if (!(error instanceof ApiError) || error.status !== 401) {
              set({ error: error instanceof Error ? error.message : '初始化身份失败' })
            }
            try {
              const guest = await api.guest()
              if (generation === identityGeneration) {
                set({
                  token: '', userId: '', guestId: guest.guest_id, username: '', email: '', phone: '',
                  initialized: true, isLoading: false,
                })
              }
            } catch (guestError) {
              if (generation === identityGeneration) {
                set({
                  initialized: true,
                  isLoading: false,
                  error: guestError instanceof Error ? guestError.message : '游客身份建立失败',
                })
              }
            }
          } finally {
            if (generation === identityGeneration) initializationPromise = null
          }
        })()
        return initializationPromise
      },

      login: async (username, password) => {
        if (!username.trim() || !password) {
          set({ error: '请输入用户名和密码' })
          return false
        }
        set({ isLoading: true, error: null })
        try {
          const res = await api.login({ username: username.trim(), password })
          identityGeneration += 1
          initializationPromise = null
          set({ ...userFields(res), initialized: true, isLoading: false })
          await resetUserScopedState(true)
          return true
        } catch (error) {
          set({ isLoading: false, error: error instanceof Error ? error.message : '登录失败' })
          return false
        }
      },

      register: async (username, password, email = '', phone = '') => {
        set({ isLoading: true, error: null })
        try {
          const res = await api.register({
            username: username.trim(), password, email: email.trim(), phone: phone.trim(),
          })
          identityGeneration += 1
          initializationPromise = null
          set({ ...userFields(res), initialized: true, isLoading: false })
          await resetUserScopedState(true)
          return true
        } catch (error) {
          set({ isLoading: false, error: error instanceof Error ? error.message : '注册失败' })
          return false
        }
      },

      logout: async () => {
        set({ isLoading: true, error: null })
        try {
          const guest = await api.logout()
          identityGeneration += 1
          initializationPromise = null
          set({
            token: '', userId: '', guestId: guest.guest_id, username: '', email: '', phone: '',
            error: null, initialized: true, isLoading: false,
          })
          await resetUserScopedState(true)
          return true
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : '退出失败，请重试',
          })
          return false
        }
      },

      expireSession: () => {
        identityGeneration += 1
        initializationPromise = null
        set({ token: '', userId: '', username: '', email: '', phone: '', initialized: false })
      },
      clearError: () => set({ error: null }),
    }),
    {
      name: 'omnicart_auth',
      partialize: (state) => ({
        userId: state.userId,
        guestId: state.guestId,
        username: state.username,
        email: state.email,
        phone: state.phone,
      }),
    },
  ),
)

export function getToken(): string {
  return useAuthStore.getState().token
}

export function getEffectiveUserId(): string {
  return useAuthStore.getState().effectiveUserId()
}
