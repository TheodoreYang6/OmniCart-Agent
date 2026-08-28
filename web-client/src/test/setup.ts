import '@testing-library/jest-dom/vitest'

// Node 22+ 内置了实验性 localStorage 全局，它会遮蔽 jsdom 提供的那个；
// 而它自己在没有 --localstorage-file 时不可用（仅报 ExperimentalWarning），
// 导致 zustand persist 默认 storage 拿到 undefined，报 "reading 'setItem'"。
// 这里用 Map 支撑的 Storage 实现同时覆盖 globalThis 与 window：
// zustand 取的是裸 localStorage 标识符（解析到 globalThis），两边都得给。
function createMemoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    key: (index: number) => [...map.keys()][index] ?? null,
    getItem: (key: string) => (map.has(key) ? (map.get(key) as string) : null),
    setItem: (key: string, value: string) => {
      map.set(key, String(value))
    },
    removeItem: (key: string) => {
      map.delete(key)
    },
    clear: () => {
      map.clear()
    },
  } as Storage
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  const storage = createMemoryStorage()
  Object.defineProperty(globalThis, name, { configurable: true, writable: true, value: storage })
  Object.defineProperty(window, name, { configurable: true, writable: true, value: storage })
}

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
})
