import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
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
      { path: '/participant/reset-password', component: ParticipantAccessView },
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
  it('registers a participant with a callsign and requests email verification', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain('/participants/auth/register')
      expect(JSON.parse(String(init?.body))).toEqual({
        email: 'radio@example.test',
        callsign: 'EA7ABC',
        password: 'a sufficiently long password',
        display_name: 'Radio Operator',
      })
      return new Response(JSON.stringify({ status: 'verification_sent' }), { status: 202 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/access')
    await wrapper.findAll('button').find((button) => button.text().includes('Create account'))!.trigger('click')
    await wrapper.get('#participant-email').setValue('radio@example.test')
    await wrapper.get('#participant-callsign').setValue('EA7ABC')
    await wrapper.get('#participant-display-name').setValue('Radio Operator')
    await wrapper.get('#participant-password').setValue('a sufficiently long password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain('verification link')
    await expectAccessible(wrapper.element)
  })

  it('submits a one-time password-reset token from the reset link', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toContain('/participants/auth/reset-password')
      expect(JSON.parse(String(init?.body))).toEqual({
        token: 'single-use-reset-token',
        password: 'replacement password for user',
      })
      return new Response(JSON.stringify({ status: 'password_updated' }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/reset-password?token=single-use-reset-token')
    await wrapper.get('#participant-password').setValue('replacement password for user')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain('password has been updated')
    await expectAccessible(wrapper.element)
  })

  it('shows an accessible message when a password-reset token has expired', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { message: 'The password reset link is invalid or expired.' },
    }), { status: 400 })))
    const { wrapper } = await mountParticipant('/participant/reset-password?token=expired-reset-token')
    await wrapper.get('#participant-password').setValue('replacement password for user')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('invalid or expired')
    await expectAccessible(wrapper.element)
  })

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
    await expectAccessible(wrapper.element)
    await wrapper.get('input[name="email"]').setValue('pilot@example.test')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await expectAccessible(wrapper.element)

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
        if (url.endsWith('/participants/auth/me')) {
          return new Response(JSON.stringify({
            id: 7,
            email: 'pilot@example.test',
            display_name: 'Pilot',
            callsigns: [{ id: 1, callsign: 'EA7ABC', is_primary: true }],
            emails: [{ email: 'pilot@example.test', is_primary: true, verified: true }],
          }), { status: 200 })
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

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(router.currentRoute.value.path).toBe('/participant/entries')
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.text()).toContain('Spring Sprint')
    expect(wrapper.text()).toContain('ea7klk')
  })
})
