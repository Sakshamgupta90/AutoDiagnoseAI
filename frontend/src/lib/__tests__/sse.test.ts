import { describe, expect, it } from 'vitest'
import { createSSEParser, type SSEMessage } from '../sse'

function collect() {
  const messages: SSEMessage[] = []
  const comments: string[] = []
  const parser = createSSEParser({ onMessage: (m) => messages.push(m), onComment: (c) => comments.push(c) })
  return { parser, messages, comments }
}

describe('createSSEParser', () => {
  it('parses typed events with JSON data', () => {
    const { parser, messages } = collect()
    parser.push('event: step\ndata: {"step_no":1,"tool_used":"vin_decode","key_inputs":{}}\n\n')
    expect(messages).toEqual([{ event: 'step', data: '{"step_no":1,"tool_used":"vin_decode","key_inputs":{}}', id: undefined }])
  })

  it('handles events split across chunks', () => {
    const { parser, messages } = collect()
    parser.push('event: confi')
    parser.push('dence\ndata: {"val')
    parser.push('ue":0.8}\n')
    expect(messages).toHaveLength(0)
    parser.push('\n')
    expect(messages[0]).toMatchObject({ event: 'confidence', data: '{"value":0.8}' })
  })

  it('reports heartbeat comments without emitting events', () => {
    const { parser, messages, comments } = collect()
    parser.push(': heartbeat\n\n')
    expect(messages).toHaveLength(0)
    expect(comments).toEqual(['heartbeat'])
  })

  it('joins multi-line data and tracks the last event id', () => {
    const { parser, messages } = collect()
    parser.push('id: 7\nevent: done\ndata: {"a":\ndata: 1}\n\n')
    expect(messages[0]).toEqual({ event: 'done', data: '{"a":\n1}', id: '7' })
    expect(parser.lastEventId).toBe('7')
  })

  it('accepts CRLF line endings and defaults the event name', () => {
    const { parser, messages } = collect()
    parser.push('data: hello\r\n\r\n')
    expect(messages[0]).toMatchObject({ event: 'message', data: 'hello' })
  })
})
