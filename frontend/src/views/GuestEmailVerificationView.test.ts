import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import GuestEmailVerificationView from './GuestEmailVerificationView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('GuestEmailVerificationView', () => {
  it('consumes the one-time token, keeps an entry grant in session storage, and scrubs the URL', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({ token: 'one-time-verification-token' })
      return new Response(
        JSON.stringify({
          status: 'verified',
          entry_id: 42,
          entry_access_token: 'entry-scoped-access-token',
          results_notifications_enabled: false,
        }),
        { status: 200 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/guest/email/verify',
          component: GuestEmailVerificationView,
        },
      ],
    })
    await router.push('/guest/email/verify?token=one-time-verification-token')
    await router.isReady()
    const wrapper = mount(GuestEmailVerificationView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('Your email address is verified.')
    expect(wrapper.text()).toContain('Result publication notices were not selected')
    expect(sessionStorage.getItem('contestmaster-entry-42')).toBe('entry-scoped-access-token')
    expect(router.currentRoute.value.fullPath).toBe('/guest/email/verify')
    expect(wrapper.get('a').attributes('href')).toBe('/entries/42/manage')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await expectAccessible(wrapper.element)
  })

  it('reports an expired or reused verification link accessibly', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ error: { message: 'This verification link is invalid, expired, or already used.' } }),
            { status: 400 },
          ),
      ),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/guest/email/verify',
          component: GuestEmailVerificationView,
        },
      ],
    })
    await router.push('/guest/email/verify?token=expired-verification-token')
    await router.isReady()
    const wrapper = mount(GuestEmailVerificationView, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('expired')
    expect(router.currentRoute.value.fullPath).toBe('/guest/email/verify')
    await expectAccessible(wrapper.element)
  })
})
