/**
 * 全局配置。
 *
 * API_BASE 解析优先级：
 *  1. 构建时注入的 VITE_API_BASE（生产部署时指定后端地址）
 *  2. 为空则使用相对路径 ''，配合 Vite 开发代理(/api → 后端) 或同源部署
 *
 * 对应安卓端 AppConfig.BASE_URL（BuildConfig.BASE_URL = http://8.137.187.54:8006/）。
 */
const rawBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export const API_BASE = rawBase.replace(/\/+$/, '')

/** 拼接 API 完整地址。 */
export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${p}`
}

/**
 * 将后端返回的相对图片地址(如 /api/products/xxx/image、/api/uploads/xxx.png)
 * 解析为可直接用于 <img src> 的绝对地址。
 * 已经是 http(s) 的直接返回。
 */
export function resolveImageUrl(url?: string | null): string {
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) {
    return url
  }
  return apiUrl(url)
}

export const APP_NAME = 'OmniCart'
export const AGENT_NAME = '欧米'
export const AGENT_EN_NAME = 'Omi'
export const AGENT_TAGLINE = '你的专属购物小助手'
export const AGENT_SLOGAN = '有欧米，购物没烦恼'
export const REQUEST_TIMEOUT_MS = 60_000
