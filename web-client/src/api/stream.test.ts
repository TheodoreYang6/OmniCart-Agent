import { afterEach, describe, expect, it, vi } from 'vitest'
import { connectStream, parseSseFrames } from './stream'

afterEach(() => vi.unstubAllGlobals())

describe('parseSseFrames', () => {
  it('keeps a partial frame for the next network chunk', () => {
    const first = parseSseFrames('event: token\ndata: {"text":"欧')
    expect(first.events).toEqual([])
    const second = parseSseFrames(`${first.rest}米"}\n\nevent: done\ndata: {"finish_reason":"stop"}\n\n`)
    expect(second.events).toEqual([
      { type: 'token', data: '{"text":"欧米"}' },
      { type: 'done', data: '{"finish_reason":"stop"}' },
    ])
  })

  it('joins multiline data and accepts CRLF frames', () => {
    const parsed = parseSseFrames('event: status\r\ndata: first\r\ndata: second\r\n\r\n')
    expect(parsed.events).toEqual([{ type: 'status', data: 'first\nsecond' }])
  })

  it('flushes a final event without a trailing blank line', () => {
    expect(parseSseFrames('event: token\ndata: tail', true).events).toEqual([
      { type: 'token', data: 'tail' },
    ])
  })

  it('ignores comments and metadata while accepting valueless data fields', () => {
    expect(parseSseFrames(': heartbeat\nretry: 1000\n\n').events).toEqual([])
    expect(parseSseFrames('event\ndata\n\n').events).toEqual([{ type: '', data: '' }])
    expect(parseSseFrames('   \n\n', true)).toEqual({ events: [], rest: '' })
  })

  it('dispatches all event types across UTF-8 chunks and completes once', async () => {
    const encoded = new TextEncoder().encode(
      'event: token\ndata: {"text":"欧米"}\n\n' +
      'event: status\ndata: {"message":"分析中"}\n\n' +
      'event: result\ndata: {"answer":"完成","products":[]}\n\n',
    )
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoded.slice(0, 24))
        controller.enqueue(encoded.slice(24))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const handlers = { onToken: vi.fn(), onStatus: vi.fn(), onResult: vi.fn(), onDone: vi.fn() }
    const stream = connectStream({ message: '推荐' }, handlers)
    await expect(stream.done).resolves.toBe('complete')
    expect(handlers.onToken).toHaveBeenCalledWith('欧米')
    expect(handlers.onStatus).toHaveBeenCalledWith('分析中')
    expect(handlers.onResult).toHaveBeenCalledWith(expect.objectContaining({ answer: '完成' }))
    expect(handlers.onDone).toHaveBeenCalledTimes(1)
  })

  it('reports server and malformed event errors', async () => {
    const onError = vi.fn()
    const unauthorized = vi.fn()
    window.addEventListener('omnicart:unauthorized', unauthorized)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '请登录' }), {
      status: 401, headers: { 'Content-Type': 'application/json' },
    })))
    await expect(connectStream({ message: 'x' }, { onError, onResult: vi.fn() }).done).resolves.toBe('error')
    expect(onError).toHaveBeenCalledWith('请登录')
    expect(unauthorized).toHaveBeenCalledOnce()
    window.removeEventListener('omnicart:unauthorized', unauthorized)

    const body = new Response('event: result\ndata: not-json\n\nevent: error\ndata: broken\n\n').body
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    onError.mockClear()
    await expect(connectStream({ message: 'x' }, { onError, onResult: vi.fn() }).done).resolves.toBe('error')
    expect(onError).toHaveBeenCalledWith('服务返回了无效的结果数据')
    expect(onError).toHaveBeenCalledWith('服务异常')
  })

  it('distinguishes user abort from read failures', async () => {
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    })))
    const onDone = vi.fn()
    const active = connectStream({ message: 'x' }, { onDone })
    active.abort()
    await expect(active.done).resolves.toBe('aborted')
    expect(onDone).toHaveBeenCalledWith('aborted')

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('socket closed')))
    const onError = vi.fn()
    await expect(connectStream({ message: 'x' }, { onError }).done).resolves.toBe('error')
    expect(onError).toHaveBeenCalledWith('socket closed')
  })
})
