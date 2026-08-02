/**
 * 认证状态 — 对应安卓端 AuthManager.kt + AuthViewModel.kt。
 *
 * - token / user 信息持久化到 localStorage
 * - deviceUserId：未登录时的设备级匿名 ID（保证不同浏览器数据隔离）
 * - effectiveUserId：已登录用真实 ID，否则用设备匿名 ID
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '@/api/client'
import type { AuthResponse } from '@/api/types'

interface AuthState {
  token: string
  userId: string
  username: string
  email: string
  phone: string
  deviceUserId: string
  isLoading: boolean
  error: string | null

  isLoggedIn: () => boolean
  effectiveUserId: () => string

  login: (username: string, password: string) => Promise<boolean>
  register: (
    username: string,
    password: string,
    email?: string,
    phone?: string,
  ) => Promise<boolean>
  logout: () => void
  clearError: () => void
}

function genDeviceId(): string {
  const rand =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10)
  return `device_${rand}`
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: '',
      userId: '',
      username: '',
      email: '',
      phone: '',
      deviceUserId: genDeviceId(),
      isLoading: false,
      error: null,

      isLoggedIn: () => get().token.trim().length > 0,
      effectiveUserId: () => {
        const s = get()
        return s.userId.trim() || s.deviceUserId
      },

      login: async (username, password) => {
        if (!username.trim() || !password.trim()) {
          set({ error: '请输入用户名和密码' })
          return false
        }
        set({ isLoading: true, error: null })
        try {
          const res: AuthResponse = await api.login({ username: username.trim(), password })
          if (res.error) {
            set({ isLoading: false, error: '用户名或密码错误' })
            return false
          }
          set({
            isLoading: false,
            token: res.token,
            userId: res.user_id,
            username: res.username,
            email: res.email ?? '',
            phone: res.phone ?? '',
          })
          return true
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : '登录失败' })
          return false
        }
      },

      register: async (username, password, email = '', phone = '') => {
        if (!username.trim() || !password.trim()) {
          set({ error: '请输入用户名和密码' })
          return false
        }
        set({ isLoading: true, error: null })
        try {
          const res: AuthResponse = await api.register({
            username: username.trim(),
            password,
            email: email.trim(),
            phone: phone.trim(),
          })
          if (res.error) {
            set({ isLoading: false, error: '用户名已存在' })
            return false
          }
          set({
            isLoading: false,
            token: res.token,
            userId: res.user_id,
            username: res.username,
            email: res.email ?? '',
            phone: res.phone ?? '',
          })
          return true
        } catch (e) {
          set({ isLoading: false, error: e instanceof Error ? e.message : '注册失败' })
          return false
        }
      },

      logout: () =>
        set({ token: '', userId: '', username: '', email: '', phone: '', error: null }),

      clearError: () => set({ error: null }),
    }),
    {
      name: 'omnicart_auth',
      partialize: (s) => ({
        token: s.token,
        userId: s.userId,
        username: s.username,
        email: s.email,
        phone: s.phone,
        deviceUserId: s.deviceUserId,
      }),
    },
  ),
)

/** 供非 React 模块（api/client、api/stream）读取当前 token。 */
export function getToken(): string {
  return useAuthStore.getState().token
}

/** 供非 React 模块读取当前有效用户 ID。 */
export function getEffectiveUserId(): string {
  return useAuthStore.getState().effectiveUserId()
}
