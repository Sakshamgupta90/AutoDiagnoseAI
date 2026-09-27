export type ApiErrorCode =
  | 'network'
  | 'timeout'
  | 'validation'
  | 'payload_too_large'
  | 'rate_limited'
  | 'unauthorized'
  | 'not_found'
  | 'server'
  | 'stream'
  | 'incomplete'
  | 'unknown'

interface ApiErrorOptions {
  code?: ApiErrorCode
  status?: number
  retryable?: boolean
}

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status?: number
  readonly retryable: boolean

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code ?? 'unknown'
    this.status = options.status
    this.retryable = options.retryable ?? true
  }
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && (err.name === 'AbortError' || err.name === 'TimeoutError')
}

/** Pulls a readable message out of FastAPI's `{detail: string | [{msg}]}` error body. */
function fastApiDetail(body: unknown): string | null {
  if (!body || typeof body !== 'object' || !('detail' in body)) return null
  const detail = (body as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : null))
      .filter(Boolean)
    if (msgs.length) return msgs.join('; ')
  }
  return null
}

export async function errorFromResponse(res: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await res.clone().json()
  } catch {
    /* non-JSON error body */
  }
  const detail = fastApiDetail(body)
  const status = res.status

  if (status === 401 || status === 403)
    return new ApiError('Your session is not authorised to use the diagnosis service. Sign in again or check the API key.', { code: 'unauthorized', status, retryable: false })
  if (status === 404)
    return new ApiError(detail ?? 'That diagnosis job could not be found. It may have expired.', { code: 'not_found', status, retryable: false })
  if (status === 413)
    return new ApiError('The photos are too large for the server. Try fewer or smaller photos.', { code: 'payload_too_large', status, retryable: false })
  if (status === 422 || status === 400)
    return new ApiError(detail ?? 'Some of the details were not accepted. Check the VIN, fault codes and description.', { code: 'validation', status, retryable: false })
  if (status === 429)
    return new ApiError('The diagnosis service is busy or today’s usage limit was reached. Wait a moment and try again.', { code: 'rate_limited', status })
  if (status >= 500)
    return new ApiError(detail ?? `The diagnosis service had a problem (HTTP ${status}). Try again shortly.`, { code: 'server', status })
  return new ApiError(detail ?? `Unexpected response from the server (HTTP ${status}).`, { code: 'unknown', status })
}

export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err
  if (err instanceof DOMException && err.name === 'TimeoutError')
    return new ApiError('The server took too long to respond.', { code: 'timeout' })
  if (err instanceof TypeError)
    return new ApiError('Can’t reach the diagnosis service. Check your connection and try again.', { code: 'network' })
  if (err instanceof Error) return new ApiError(err.message)
  return new ApiError('Something went wrong.')
}
