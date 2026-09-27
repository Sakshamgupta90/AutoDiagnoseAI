export interface SSEMessage {
  event: string
  data: string
  id?: string
}

export interface SSEParserHandlers {
  onMessage: (message: SSEMessage) => void
  /** Called for `: comment` lines — the backend's 15s heartbeat. */
  onComment?: (text: string) => void
}

/**
 * Incremental parser for the text/event-stream format. Feed it decoded text
 * chunks as they arrive; it dispatches complete events on blank lines.
 */
export function createSSEParser({ onMessage, onComment }: SSEParserHandlers) {
  let buffer = ''
  let eventName = ''
  let dataLines: string[] = []
  let lastId: string | undefined

  function dispatch() {
    if (dataLines.length > 0) {
      onMessage({ event: eventName || 'message', data: dataLines.join('\n'), id: lastId })
    }
    eventName = ''
    dataLines = []
  }

  function processLine(line: string) {
    if (line === '') return dispatch()
    if (line.startsWith(':')) return onComment?.(line.slice(1).trim())

    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    if (field === 'event') eventName = value
    else if (field === 'data') dataLines.push(value)
    else if (field === 'id') lastId = value
  }

  return {
    push(chunk: string) {
      buffer += chunk
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      lines.forEach(processLine)
    },
    get lastEventId() {
      return lastId
    },
  }
}
