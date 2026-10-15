import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import ParticipantAccessView from './ParticipantAccessView.vue'

afterEach(() => vi.unstubAllGlobals())

async function mountParticipant(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/participant/access', component: ParticipantAccessView },
      { path: '/participant/verify', component: ParticipantAccessView },
      { path: '/participant/entries', component: ParticipantAccessView },
    ],
  })
  await router.push(path)
  await router.isReady()
  return {
    wrapper: mount(ParticipantAccessView, { global: { plugins: [router] } }),
    router,
  }
}

describe('ParticipantAccessView', () => {
  it('requests a magic link without disclosing whether an email is registered', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        expect(init?.method).toBe('POST')
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'pilot@example.test',
        })
        return new Response(
          JSON.stringify({
            status: 'accepted',
            message: 'If the address can be used, a link was sent.',
          }),
          { status: 202 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/access')
    await wrapper.get('input[name="email"]').setValue('pilot@example.test')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain(
      'one-time sign-in link',
    )
  })

  it('consumes the emailed token, removes it from the URL, and lists scoped entries', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/participants/auth/consume-link')) {
          expect(JSON.parse(String(init?.body))).toEqual({
            token: 'secret-link-token',
          })
          return new Response(
            JSON.stringify({ csrf_token: 'participant-csrf' }),
            { status: 200 },
          )
        }
        expect(url).toContain('/participants/auth/entries')
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 4,
                contest_id: 9,
                contest_name: 'Spring Sprint',
                contest_slug: 'spring-sprint',
                entry_key: 'ea7klk',
                status: 'received',
                submitted_at: '2026-05-01T00:00:00Z',
              },
            ],
          }),
          { status: 200 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper, router } = await mountParticipant(
      '/participant/verify?token=secret-link-token',
    )
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.path).toBe('/participant/entries')
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.text()).toContain('Spring Sprint')
    expect(wrapper.text()).toContain('ea7klk')
  })
})
