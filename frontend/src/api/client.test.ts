import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from './client'
import { setLocale } from '../i18n'

afterEach(() => vi.unstubAllGlobals())

describe('shared API client', () => {
  it('sends same-origin credentials and the readable CSRF cookie on mutations', async () => {
    const cookieDescriptor = Object.getOwnPropertyDescriptor(document, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      value: 'contestmaster_csrf=csrf-token',
    })
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        const headers = new Headers(init?.headers)
        expect(init?.credentials).toBe('same-origin')
        expect(headers.get('X-CSRF-Token')).toBe('csrf-token')
        return new Response(JSON.stringify({ saved: true }), { status: 200 })
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      apiRequest('/contests/1', {
        method: 'PUT',
        body: JSON.stringify({ name: 'Test' }),
      }),
    ).resolves.toEqual({ saved: true })

    vi.unstubAllGlobals()
    if (cookieDescriptor) {
      Object.defineProperty(document, 'cookie', cookieDescriptor)
    } else {
      Reflect.deleteProperty(document, 'cookie')
    }
  })

  it('converts the standard API error envelope to a typed error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                message: 'Contest not found.',
                details: [
                  {
                    location: ['path', 'contest_id'],
                    message: 'Missing.',
                    type: 'not_found',
                  },
                ],
              },
            }),
            { status: 404 },
          ),
      ),
    )

    await expect(apiRequest('/contests/99')).rejects.toMatchObject({
      name: 'ApiError',
      message: 'Contest not found.',
      statusCode: 404,
      issues: [{ message: 'Missing.' }],
    })
  })

  it('localizes known API error messages in the active interface language', async () => {
    await setLocale('de', undefined)
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        expect(new Headers(init?.headers).get('Accept-Language')).toBe('de')
        return new Response(
          JSON.stringify({ error: { message: 'Authentication is required.' } }),
          { status: 401 },
        )
      },
    )
    vi.stubGlobal(
      'fetch',
      fetchMock,
    )

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({
      message: 'Eine Anmeldung ist erforderlich.',
    })
    await setLocale('en', undefined)
  })

  it('uses the separate participant CSRF cookie for participant mutations', async () => {
    const cookieDescriptor = Object.getOwnPropertyDescriptor(document, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      value:
        'contestmaster_csrf=staff-token; contestmaster_participant_csrf=participant-token',
    })
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe(
          'participant-token',
        )
        return new Response(JSON.stringify({ status: 'signed_out' }), {
          status: 200,
        })
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/participants/auth/logout', { method: 'POST' })

    vi.unstubAllGlobals()
    if (cookieDescriptor)
      Object.defineProperty(document, 'cookie', cookieDescriptor)
    else Reflect.deleteProperty(document, 'cookie')
  })
})
