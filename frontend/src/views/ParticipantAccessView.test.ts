import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setParticipantSession } from '../state/participantSession'
import ParticipantAccessView from './ParticipantAccessView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  setParticipantSession(null)
})

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
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        expect(String(input)).toContain('/participants/auth/register')
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'radio@example.test',
          callsign: 'EA7ABC',
          password: 'a sufficiently long password',
          display_name: 'Radio Operator',
        })
        return new Response(JSON.stringify({ status: 'verification_sent' }), {
          status: 202,
        })
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/access')
    const modeButtons = wrapper.findAll('.participant-mode-button')
    expect(modeButtons).toHaveLength(3)
    expect(
      modeButtons.every((button) =>
        button.classes().includes('secondary-button'),
      ),
    ).toBe(true)
    expect(modeButtons[0].attributes('aria-pressed')).toBe('true')
    expect(modeButtons[0].classes()).toContain('is-active')
    expect(modeButtons[2].attributes('aria-pressed')).toBe('false')
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Create account'))!
      .trigger('click')
    expect(
      wrapper.findAll('.participant-mode-button')[2].attributes('aria-pressed'),
    ).toBe('true')
    expect(wrapper.findAll('.participant-mode-button')[2].classes()).toContain(
      'is-active',
    )
    await wrapper.get('#participant-email').setValue('radio@example.test')
    await wrapper.get('#participant-callsign').setValue('EA7ABC')
    await wrapper.get('#participant-display-name').setValue('Radio Operator')
    await wrapper
      .get('#participant-password')
      .setValue('a sufficiently long password')
    expect(wrapper.get('.participant-submit-button').classes()).toContain(
      'primary-button',
    )
    expect(wrapper.text()).toContain('Registration is optional')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain('verification email')
    await expectAccessible(wrapper.element)
  })

  it('submits a one-time password-reset token from the reset link', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        expect(String(input)).toContain('/participants/auth/reset-password')
        expect(JSON.parse(String(init?.body))).toEqual({
          token: 'single-use-reset-token',
          password: 'replacement password for user',
        })
        return new Response(JSON.stringify({ status: 'password_updated' }), {
          status: 200,
        })
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant(
      '/participant/reset-password?token=single-use-reset-token',
    )
    await wrapper
      .get('#participant-password')
      .setValue('replacement password for user')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(wrapper.get('[role="status"]').text()).toContain(
      'password has been updated',
    )
    await expectAccessible(wrapper.element)
  })

  it('shows an accessible message when a password-reset token has expired', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: {
                message: 'The password reset link is invalid or expired.',
              },
            }),
            { status: 400 },
          ),
      ),
    )
    const { wrapper } = await mountParticipant(
      '/participant/reset-password?token=expired-reset-token',
    )
    await wrapper
      .get('#participant-password')
      .setValue('replacement password for user')
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
      'sign-in email will arrive shortly',
    )
  })

  it('promotes an attached callsign and protects the active primary from removal', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/participants/auth/entries')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 })
      }
      if (url.endsWith('/participants/auth/me')) {
        return new Response(
          JSON.stringify({
            id: 7,
            email: 'pilot@example.test',
            display_name: 'Pilot',
            callsigns: [
              { id: 1, callsign: 'EA7ABC', is_primary: true },
              { id: 2, callsign: 'K1XYZ', is_primary: false },
            ],
            emails: [],
          }),
          { status: 200 },
        )
      }
      expect(url).toContain('/participants/auth/callsigns/2/primary')
      expect(init?.method).toBe('PATCH')
      return new Response(
        JSON.stringify({ id: 2, callsign: 'K1XYZ', is_primary: true }),
        { status: 200 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/entries')
    await flushPromises()

    const primaryRow = () =>
      wrapper
        .findAll('.participant-callsigns li')
        .find((item) => item.text().includes('K1XYZ'))!
    expect(wrapper.text()).toContain('EA7ABC')
    expect(primaryRow().text()).toContain('Set as primary')
    await primaryRow().get('button').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain(
      'Primary callsign updated.',
    )
    expect(primaryRow().text()).toContain('Primary')
    expect(primaryRow().find('button').exists()).toBe(false)
    expect(
      wrapper
        .findAll('.participant-callsigns li')
        .find((item) => item.text().includes('EA7ABC'))
        ?.text(),
    ).toContain('Set as primary')
    await expectAccessible(wrapper.element)
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
          return new Response(
            JSON.stringify({
              id: 7,
              email: 'pilot@example.test',
              display_name: 'Pilot',
              callsigns: [{ id: 1, callsign: 'EA7ABC', is_primary: true }],
              emails: [
                {
                  email: 'pilot@example.test',
                  is_primary: true,
                  verified: true,
                },
              ],
            }),
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

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(router.currentRoute.value.path).toBe('/participant/entries')
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.text()).toContain('Spring Sprint')
    expect(wrapper.text()).toContain('ea7klk')
    expect(wrapper.get('.participant-access-card').classes()).toContain(
      'is-signed-in',
    )
    expect(
      wrapper
        .get('.participant-dashboard .section-heading-row .secondary-button')
        .text(),
    ).toContain('Sign out')
    expect(wrapper.find('.participant-entries-table').exists()).toBe(true)
    await expectAccessible(wrapper.element)
  })

  it('claims guest logs with a receipt token and refreshes the entry list', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        calls.push({ url, init })
        if (url.endsWith('/participants/auth/entries')) {
          const claimed = calls.some((call) =>
            call.url.endsWith('/participants/auth/claim-entries'),
          )
          return new Response(
            JSON.stringify({
              items: claimed
                ? [
                    {
                      id: 12,
                      contest_id: 3,
                      contest_name: 'Summer Test',
                      contest_slug: 'summer-test',
                      entry_key: 'ea7abc',
                      status: 'accepted',
                      submitted_at: '2026-07-01T00:00:00Z',
                    },
                  ]
                : [],
            }),
            { status: 200 },
          )
        }
        if (url.endsWith('/participants/auth/me')) {
          return new Response(
            JSON.stringify({
              id: 7,
              email: 'pilot@example.test',
              display_name: 'Pilot',
              callsigns: [{ id: 1, callsign: 'EA7ABC', is_primary: true }],
              emails: [
                {
                  email: 'pilot@example.test',
                  is_primary: true,
                  verified: true,
                },
              ],
            }),
            { status: 200 },
          )
        }
        expect(url).toContain('/participants/auth/claim-entries')
        expect(JSON.parse(String(init?.body))).toEqual({
          receipt_token: 'my-private-entry-receipt-token',
        })
        return new Response(
          JSON.stringify({
            status: 'claimed',
            callsign: 'EA7ABC',
            claimed_entries: 1,
          }),
          { status: 200 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/entries')
    await flushPromises()
    await wrapper
      .get('#guest-entry-receipt')
      .setValue('my-private-entry-receipt-token')
    await wrapper.get('#claim-guest-logs-form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('Guest logs linked to EA7ABC: 1')
    expect(wrapper.text()).toContain('Summer Test')
    expect(
      (wrapper.get('#guest-entry-receipt').element as HTMLInputElement).value,
    ).toBe('')
    await expectAccessible(wrapper.element)
  })

  it('retains the receipt input and reports an inaccessible or invalid claim safely', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/participants/auth/entries')) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 })
      }
      if (url.endsWith('/participants/auth/me')) {
        return new Response(
          JSON.stringify({
            id: 7,
            email: 'pilot@example.test',
            display_name: 'Pilot',
            callsigns: [{ id: 1, callsign: 'EA7ABC', is_primary: true }],
            emails: [],
          }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({
          error: { message: 'Entry not found or access is no longer valid.' },
        }),
        { status: 404 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountParticipant('/participant/entries')
    await flushPromises()
    await wrapper
      .get('#guest-entry-receipt')
      .setValue('invalid-receipt-token-value')
    await wrapper.get('#claim-guest-logs-form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Entry not found')
    expect(
      (wrapper.get('#guest-entry-receipt').element as HTMLInputElement).value,
    ).toBe('invalid-receipt-token-value')
    await expectAccessible(wrapper.element)
  })
})
