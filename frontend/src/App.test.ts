import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from './App.vue'
import { expectAccessible } from './test/a11y'

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
      routes: [
        { path: '/', component: { template: '<p>Home</p>' } },
        {
          path: '/:pathMatch(.*)*',
          component: { template: '<p>Not found</p>' },
        },
      ],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Sign out Contest Manager')
    expect(wrapper.text()).not.toContain('Master data')
    await wrapper.get('.sign-out-button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Staff sign-in')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    if (originalCookie)
      Object.defineProperty(document, 'cookie', originalCookie)
    else Reflect.deleteProperty(document, 'cookie')
  })

  it('opens and closes the responsive navigation with Escape and route selection', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { message: 'Authentication is required.' },
            }),
            { status: 401 },
          ),
      ),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<p>Published results</p>' } },
        {
          path: '/manage/contests',
          component: { template: '<p>Manage contests</p>' },
        },
        { path: '/submit-log', component: { template: '<p>Submit a log</p>' } },
        { path: '/sign-in', component: { template: '<p>Staff sign-in</p>' } },
        { path: '/rulesets/compose', component: { template: '<p>Rules</p>' } },
        {
          path: '/participant/access',
          component: { template: '<p>Participant access</p>' },
        },
        {
          path: '/:pathMatch(.*)*',
          component: { template: '<p>Not found</p>' },
        },
      ],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [router] },
    })
    await flushPromises()

    const trigger = wrapper.get('.menu-toggle')
    const nav = wrapper.get('#main-navigation')
    expect(trigger.attributes('aria-controls')).toBe('main-navigation')
    expect(trigger.attributes('aria-label')).toBe('Open main menu')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('.header-upload-action').attributes('href')).toBe(
      '/submit-log',
    )

    await trigger.trigger('click')
    expect(trigger.attributes('aria-label')).toBe('Close main menu')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(nav.classes()).toContain('is-open')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(trigger.attributes('aria-label')).toBe('Open main menu')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)

    await trigger.trigger('click')
    await wrapper.get('a[href="/manage/contests"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/manage/contests')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.text()).toContain('Submit a log')
    await expectAccessible(wrapper.element)
    wrapper.unmount()
  })

  it('keeps master-data administration links exclusive to global administrators', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              id: 1,
              username: 'admin',
              email: 'admin@example.test',
              display_name: 'Global Admin',
              role: 'global_administrator',
            }),
            { status: 200 },
          ),
      ),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<p>Home</p>' } }],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('a[href="/admin/master-data"]').text()).toBe(
      'Master data',
    )
    expect(wrapper.get('a[href="/admin/operating-catalog"]').text()).toBe(
      'Bands and modes',
    )
    expect(wrapper.find('a[href="/sign-in"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
