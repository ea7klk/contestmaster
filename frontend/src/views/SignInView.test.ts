import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import SignInView from './SignInView.vue'

afterEach(() => vi.unstubAllGlobals())

async function mountSignIn(path = '/sign-in?next=/manage/contests') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/sign-in', component: SignInView },
      { path: '/reset-password', component: SignInView },
      { path: '/change-password', component: { template: '<p>change password</p>' } },
      {
        path: '/manage/contests',
        component: { template: '<p>manager home</p>' },
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  return {
    wrapper: mount(SignInView, { global: { plugins: [router] } }),
    router,
  }
}

describe('SignInView', () => {
  it('submits credentials through the shared client and navigates to the requested route', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        expect(init?.method).toBe('POST')
        expect(init?.credentials).toBe('same-origin')
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'manager@example.test',
          password: 'strong passphrase',
        })
        return new Response(
          JSON.stringify({
            user: {
              id: 8,
              username: 'manager',
              email: 'manager@example.test',
              display_name: 'Contest Manager',
              role: 'contest_manager',
              must_change_password: false,
            },
            csrf_token: 'csrf-secret',
          }),
          { status: 200 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper, router } = await mountSignIn()
    await wrapper.get('input[name="email"]').setValue('manager@example.test')
    await wrapper.get('input[name="password"]').setValue('strong passphrase')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/manage/contests')
  })

  it('routes an account with a required first-login password change to the change screen', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      user: {
        id: 8,
        username: 'manager',
        email: 'manager@example.test',
        display_name: 'Contest Manager',
        role: 'contest_admin',
        must_change_password: true,
      },
      csrf_token: 'csrf-secret',
    }), { status: 200 })))
    const { wrapper, router } = await mountSignIn('/sign-in?next=/admin/users')
    await wrapper.get('input[name="email"]').setValue('manager@example.test')
    await wrapper.get('input[name="password"]').setValue('initial password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/change-password')
    expect(router.currentRoute.value.query.next).toBe('/admin/users')
  })

  it('shows a server error accessibly without navigating', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { message: 'Email or password is incorrect.' },
            }),
            { status: 401 },
          ),
      ),
    )
    const { wrapper, router } = await mountSignIn()
    await wrapper.get('input[name="email"]').setValue('manager@example.test')
    await wrapper.get('input[name="password"]').setValue('incorrect')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain(
      'password is incorrect',
    )
    expect(router.currentRoute.value.path).toBe('/sign-in')
  })

  it('requests a generic staff password recovery message', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({ email: 'staff@example.test' })
      return new Response(JSON.stringify({
        status: 'accepted',
        message: 'If the account is eligible, a password reset link was sent.',
      }), { status: 202 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountSignIn()
    await wrapper.findAll('button').find((button) => button.text().includes('Forgot password'))!.trigger('click')
    await wrapper.get('input[name="email"]').setValue('staff@example.test')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain('If the account is eligible')
  })

  it('consumes a one-time staff password-reset token', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        token: 'staff-reset-token',
        password: 'a sufficiently long replacement password',
      })
      return new Response(JSON.stringify({ status: 'password_updated' }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountSignIn('/reset-password?token=staff-reset-token')
    await wrapper.get('input[type="password"]').setValue('a sufficiently long replacement password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain('password has been updated')
  })
})
