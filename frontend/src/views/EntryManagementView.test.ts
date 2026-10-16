import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import EntryManagementView from './EntryManagementView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('EntryManagementView', () => {
  it('uses the tab-scoped receipt token and appends contact removals as revisions', async () => {
    sessionStorage.setItem('contestmaster-entry-4', 'receipt-secret')
    let revision = 1
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        expect(new Headers(init?.headers).get('X-Entry-Receipt')).toBe(
          'receipt-secret',
        )
        if (init?.method === 'DELETE') {
          revision = 2
          return new Response(
            JSON.stringify({
              entry_id: 4,
              contest_id: 1,
              accepted_formats: ['adif'],
              entry_key: 'entry-4',
              category_values: {},
              revision_number: revision,
              contacts: [],
            }),
            { status: 200 },
          )
        }
        expect(path).toMatch(/\/public\/entries\/4$/)
        return new Response(
          JSON.stringify({
            entry_id: 4,
            contest_id: 1,
            accepted_formats: ['adif'],
            entry_key: 'entry-4',
            category_values: {},
            revision_number: revision,
            contacts: [
              {
                id: 9,
                occurred_at: '2026-10-15T12:34:00Z',
                callsign: 'F4ABC',
                frequency: '14025',
                mode: 'CW',
                exchange_sent: { raw: '001' },
                exchange_received: { raw: '002' },
              },
            ],
          }),
          { status: 200 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/entries/:entryId/manage', component: EntryManagementView },
      ],
    })
    await router.push('/entries/4/manage')
    await router.isReady()
    const wrapper = mount(EntryManagementView, {
      global: { plugins: [router] },
    })
    await flushPromises()
    await expectAccessible(wrapper.element)

    expect(wrapper.text()).toContain('F4ABC')
    expect(wrapper.get('#revision-file').attributes('accept')).toBe(
      '.adi,.adif',
    )
    expect(wrapper.get('label[for="revision-file"]').text()).toBe(
      'Corrected log file (ADI/ADIF)',
    )
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Remove')
      ?.trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('Revision 2 saved.')
    expect(wrapper.text()).toContain('No contacts in this revision.')
  })

  it('renders untrusted imported callsigns as text instead of executable markup', async () => {
    const hostileCall = '<img src=x onerror=alert(1)>'
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              entry_id: 4,
              contest_id: 1,
              entry_key: 'entry-4',
              category_values: {},
              revision_number: 1,
              contacts: [
                {
                  id: 9,
                  occurred_at: '2026-10-15T12:34:00Z',
                  callsign: hostileCall,
                  frequency: '14025',
                  mode: 'CW',
                  exchange_sent: {},
                  exchange_received: {},
                },
              ],
            }),
            { status: 200 },
          ),
      ),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/entries/:entryId/manage', component: EntryManagementView },
      ],
    })
    await router.push('/entries/4/manage')
    await router.isReady()
    const wrapper = mount(EntryManagementView, {
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain(hostileCall)
    expect(wrapper.find('img').exists()).toBe(false)
  })
})
