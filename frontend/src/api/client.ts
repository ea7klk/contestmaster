export interface ApiIssue {
  location: Array<string | number>
  message: string
  type: string
}

export class ApiError extends Error {
  readonly issues: ApiIssue[]
  readonly statusCode: number | undefined

  constructor(message: string, issues: ApiIssue[] = [], statusCode?: number) {
    super(message)
    this.name = 'ApiError'
    this.issues = issues
    this.statusCode = statusCode
  }
}

const apiPrefix = import.meta.env.VITE_API_PREFIX ?? '/api/v1'

function csrfToken(path: string): string | undefined {
  if (typeof document === 'undefined') return undefined
  const cookieName =
    path.startsWith('/participants/auth') || path.startsWith('/public/entries')
      ? 'contestmaster_participant_csrf'
      : 'contestmaster_csrf'
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${cookieName}=([^;]+)`),
  )
  return match ? decodeURIComponent(match[1] ?? '') : undefined
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (
    !['GET', 'HEAD', 'OPTIONS'].includes(method) &&
    !headers.has('X-CSRF-Token')
  ) {
    const csrf = csrfToken(path)
    if (csrf) headers.set('X-CSRF-Token', csrf)
  }

  let response: Response
  try {
    response = await fetch(`${apiPrefix}${path}`, {
      ...init,
      method,
      headers,
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(
      'The API could not be reached. Check the connection and try again.',
    )
  }

  const payload = (await response.json().catch(() => null)) as
    { error?: { message?: string; details?: ApiIssue[] } } | T | null
  if (!response.ok) {
    const error =
      payload !== null && typeof payload === 'object' && 'error' in payload
        ? (payload as { error?: { message?: string; details?: ApiIssue[] } })
            .error
        : undefined
    throw new ApiError(
      error?.message ?? `The API returned HTTP ${response.status}.`,
      error?.details ?? [],
      response.status,
    )
  }
  return payload as T
}
