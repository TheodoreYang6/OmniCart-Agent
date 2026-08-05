export interface ParsedSseEvent {
  type: string
  data: string
}

/** Parse complete SSE frames while retaining an unfinished network tail. */
export function parseSseFrames(buffer: string, flush = false): {
  events: ParsedSseEvent[]
  rest: string
} {
  const normalized = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const blocks = normalized.split('\n\n')
  const tail = blocks.pop() ?? ''
  const rest = flush ? '' : tail
  const complete = flush && tail ? [...blocks, tail] : blocks
  const events: ParsedSseEvent[] = []

  for (const block of complete) {
    if (!block.trim()) continue
    let type = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue
      const colon = line.indexOf(':')
      const field = colon < 0 ? line : line.slice(0, colon)
      let value = colon < 0 ? '' : line.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'event') type = value
      if (field === 'data') data.push(value)
    }
    if (data.length) events.push({ type, data: data.join('\n') })
  }
  return { events, rest }
}
