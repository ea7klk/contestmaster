import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import SystemPasswordChangeView from './SystemPasswordChangeView.vue'

afterEach(() => vi.unstubAllGlobals())

describe('SystemPasswordChangeView', () => {
  it('requires matching new passwords and submits the authenticated change', async () => {
    const originalCookie = Object.getOwnPropertyDescriptor(document, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      value: 'contestmaster_csrf=csrf-token',
    })
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe('POST')
      expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('csrf-token')
      expect(JSON.parse(String(init?.body))).toEqual({
        current_password: 'Initial password',
        new_password: 'New secure password',
      })
      return new Response(JSON.stringify({ status: 'password_updated' }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/change-password', component: SystemPasswordChangeView },
        { path: '/admin/users', component: { template: '<p>admin users</p>' } },
      ],
    })
    await router.push('/change-password?next=/admin/users')
    await router.isReady()
    const wrapper = mount(SystemPasswordChangeView, { global: { plugins: [router] } })
    await expectAccessible(wrapper.element)
    await wrapper.get('#current-password').setValue('Initial password')
    await wrapper.get('#new-password').setValue('New secure password')
    await wrapper.get('#confirm-password').setValue('different password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('passwords do not match')

    await wrapper.get('#confirm-password').setValue('New secure password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/admin/users')
    wrapper.unmount()
    if (originalCookie) Object.defineProperty(document, 'cookie', originalCookie)
    else Reflect.deleteProperty(document, 'cookie')
  })

  it('shows a safe API error without clearing entered credentials', async () => {
    const originalCookie = Object.getOwnPropertyDescriptor(document, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      value: 'contestmaster_csrf=csrf-token',
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { message: 'The current password is incorrect.' },
    }), { status: 400 })))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/change-password', component: SystemPasswordChangeView }],
    })
    await router.push('/change-password')
    await router.isReady()
    const wrapper = mount(SystemPasswordChangeView, { global: { plugins: [router] } })
    await wrapper.get('#current-password').setValue('Wrong password')
    await wrapper.get('#new-password').setValue('New secure password')
    await wrapper.get('#confirm-password').setValue('New secure password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('current password is incorrect')
    expect(wrapper.get('#current-password').element).toHaveProperty('value', 'Wrong password')
    await expectAccessible(wrapper.element)
    wrapper.unmount()
    if (originalCookie) Object.defineProperty(document, 'cookie', originalCookie)
    else Reflect.deleteProperty(document, 'cookie')
  })
})
