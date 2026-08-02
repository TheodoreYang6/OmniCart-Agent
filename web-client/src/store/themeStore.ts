import { create } from 'zustand'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'omnicart-theme'

/** 读取初始主题：localStorage > 默认浅色（不跟随系统，保持电商轻快默认） */
function readInitial(): Theme {
  if (typeof window === 'undefined') return 'light'
  const saved = window.localStorage.getItem(STORAGE_KEY)
  return saved === 'dark' ? 'dark' : 'light'
}

/** 把主题写到 <html data-theme>，CSS 变量体系据此翻转 */
function apply(theme: Theme) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', theme)
  // 同步浏览器 UI 色（地址栏/状态栏）
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', theme === 'dark' ? '#0D0D14' : '#256BFF')
}

interface ThemeState {
  theme: Theme
  setTheme: (t: Theme) => void
  toggle: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: readInitial(),
  setTheme: (t) => {
    apply(t)
    window.localStorage.setItem(STORAGE_KEY, t)
    set({ theme: t })
  },
  toggle: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
}))

/** 应用启动时立即生效一次（main.tsx 调用；配合 index.html 内联脚本消除闪白） */
export function initTheme() {
  apply(useThemeStore.getState().theme)
}
