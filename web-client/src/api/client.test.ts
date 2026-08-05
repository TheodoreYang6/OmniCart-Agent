import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, request } from './client'

const jsonResponse = (body: unknown = {}, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('HTTP client', () => {
  it('serializes query/body and returns structured JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/api/example', {
      method: 'POST', query: { q: '欧米', empty: '', page: 2 }, body: { hello: 'world' },
    })).resolves.toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain('q=%E6%AC%A7%E7%B1%B3&page=2')
    expect(init).toMatchObject({ method: 'POST', credentials: 'include', body: '{"hello":"world"}' })
  })

  it('normalizes API, validation, text and network errors', async () => {
    const unauthorized = vi.fn()
    window.addEventListener('omnicart:unauthorized', unauthorized)
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(jsonResponse({ detail: '登录过期', code: 'expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: [{ msg: '字段错误' }] }, 422))
      .mockResolvedValueOnce(new Response('bad gateway', { status: 502 })))
    await expect(request('/private')).rejects.toMatchObject({ status: 401, code: 'expired', message: '登录过期' })
    await expect(request('/validation')).rejects.toMatchObject({ status: 422, message: '字段错误' })
    await expect(request('/gateway')).rejects.toMatchObject({ status: 502, message: '请求失败 (502)' })
    expect(unauthorized).toHaveBeenCalledTimes(1)
    window.removeEventListener('omnicart:unauthorized', unauthorized)

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await expect(request('/offline')).rejects.toEqual(expect.objectContaining({ status: 0, kind: 'network', message: 'offline' }))
  })

  it('distinguishes user cancellation from a request timeout', async () => {
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })))
    const controller = new AbortController()
    const cancelled = request('/cancelled', { signal: controller.signal })
    controller.abort('user')
    await expect(cancelled).rejects.toMatchObject({ status: 0, kind: 'aborted', message: '请求已取消' })
    await expect(request('/timeout', { timeoutMs: 1 })).rejects.toMatchObject({ status: 0, kind: 'timeout' })
  })

  it('handles plain successful bodies and non-Error transport failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('plain text', { status: 200 })))
    await expect(request('/plain', { body: null })).resolves.toBe('plain text')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue('socket vanished'))
    await expect(request('/unknown-network-error')).rejects.toMatchObject({ kind: 'network', message: '网络请求失败' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    await expect(request('/implicit-abort')).rejects.toMatchObject({ kind: 'aborted', message: '请求已取消' })
  })

  it('normalizes mixed validation details without trusting a non-string code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: ['直接错误', { msg: '对象错误' }], code: 42 }, 422)))
    await expect(request('/mixed-validation')).rejects.toMatchObject({
      status: 422,
      kind: 'http',
      message: '直接错误；对象错误',
      code: undefined,
    })
  })

  it('checks raw responses and exercises the typed API facade', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ items: [], conversations: [] })))
    vi.stubGlobal('fetch', fetchMock)
    await Promise.all([
      api.health(), api.getProducts({ page: 1 }), api.getProduct('p/1'), api.recommend({ user_query: 'x' }),
      api.recommendGuide({ user_query: 'x' }), api.getConversations('u'), api.getConversationMessages('c'),
      api.deleteConversation('c'), api.uploadImage(new File(['x'], 'x.png')), api.getCart({ user_id: 'u' }),
      api.addToCart({ product_id: 'p' }), api.updateCartItem('i', { quantity: 2 }), api.removeCartItem('i'),
      api.selectAllCart(true), api.clearCart(), api.checkout({ item_ids: ['i'] }), api.getOrders('u'),
      api.register({ username: 'u', password: '12345678' }), api.login({ username: 'u', password: '12345678' }),
      api.profile(), api.guest(), api.logout(), api.getAddresses('u'),
      api.createAddress({ name: 'n', phone: '13800138000' }, 'u'), api.updateAddress('a', { city: '杭州' }, 'u'),
      api.deleteAddress('a', 'u'), api.getPreferenceEntries('u'), api.parsePreference('u', '轻便'),
      api.savePreferenceEntry('u', '轻便'), api.deletePreferenceEntry('e', 'u'),
      api.togglePreferenceEntry('e', 'u', true), api.voiceTranscribe(new Blob(['voice'])),
    ])
    expect(fetchMock).toHaveBeenCalledTimes(32)

    const raw = new Response('audio', { status: 200 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(raw))
    await expect(api.voiceTTS('你好')).resolves.toBe(raw)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'TTS unavailable' }, 503)))
    await expect(api.voiceTTS('你好')).rejects.toMatchObject({ status: 503 })
  })

  it('parses product summary SSE and rejects bad status', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"text":"很"}\n\ndata: heartbeat\n\n'))
        controller.enqueue(encoder.encode('data: {"text":"好"}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const chunks: string[] = []
    await api.streamProductSummary('p', 'q', (value) => chunks.push(value))
    expect(chunks).toEqual(['很', '好'])
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 500)))
    await expect(api.streamProductSummary('p', 'q', vi.fn())).rejects.toMatchObject({ status: 500 })
  })

  it('classifies product-summary cancellation and transport failures', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })))
    const cancelled = api.streamProductSummary('p', 'q', vi.fn(), controller.signal)
    controller.abort()
    await expect(cancelled).rejects.toMatchObject({ kind: 'aborted' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('summary offline')))
    await expect(api.streamProductSummary('p', 'q', vi.fn())).rejects.toMatchObject({ kind: 'network', message: 'summary offline' })
  })
})
