import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from './App.vue'

afterEach(() => vi.unstubAllGlobals())

describe('App privileged navigation', () => {
  it('shows the active staff account and sends sign-out through the session API', async () => {
    const originalCookie = Object.getOwnPropertyDescriptor(document, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      value: 'contestmaster_csrf=csrf-token',
    })
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) {
          return new Response(
            JSON.stringify({
              id: 4,
              username: 'manager',
              email: 'manager@example.test',
              display_name: 'Contest Manager',
              role: 'contest_manager',
            }),
            { status: 200 },
          )
        }
        expect(path).toMatch(/\/auth\/logout$/)
        expect(init?.method).toBe('POST')
        expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe(
          'csrf-token',
        )
        return new Response(JSON.stringify({ status: 'signed_out' }), {
          status: 200,
        })
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<p>Home</p>' } }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('Sign out Contest Manager')
    expect(wrapper.text()).not.toContain('Master data')
    await wrapper.get('.sign-out-button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Staff sign-in')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    if (originalCookie)
      Object.defineProperty(document, 'cookie', originalCookie)
    else Reflect.deleteProperty(document, 'cookie')
  })
})
