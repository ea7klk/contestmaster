import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import SignInView from './SignInView.vue'

afterEach(() => vi.unstubAllGlobals())

async function mountSignIn() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/sign-in', component: SignInView },
      {
        path: '/manage/contests',
        component: { template: '<p>manager home</p>' },
      },
    ],
  })
  await router.push('/sign-in?next=/manage/contests')
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
})
