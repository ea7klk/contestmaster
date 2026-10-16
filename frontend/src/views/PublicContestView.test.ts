import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import PublicContestView from './PublicContestView.vue'

const details = {
  id: 8,
  name: 'Autumn Test',
  slug: 'autumn-test',
  description: 'A public contest.',
  starts_at: '2026-10-20T00:00:00Z',
  ends_at: '2026-10-20T06:00:00Z',
  log_submission_cutoff_at: '2026-10-21T00:00:00Z',
  status: 'open',
}

describe('PublicContestView', () => {
  it('shows UTC contest dates and a preselected log submission link for an open contest', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(details), { status: 200 })),
    )
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    const wrapper = mount(PublicContestView, {
      props: { slug: 'autumn-test' },
      global: { plugins: [router] },
    })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Autumn Test')
    expect(wrapper.text()).toContain('20 Oct 2026, 00:00 UTC')
    expect(wrapper.get('a.primary-button').attributes('href')).toBe(
      '/submit-log?contest=autumn-test',
    )
    await expectAccessible(wrapper.element)
  })

  it('explains when log submission has closed', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...details,
              log_submission_cutoff_at: '2026-10-15T00:00:00Z',
            }),
            { status: 200 },
          ),
      ),
    )
    const wrapper = mount(PublicContestView, {
      props: { slug: 'autumn-test' },
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain(
      'Log submissions are closed for this contest.',
    )
    expect(wrapper.find('a.primary-button').exists()).toBe(false)
  })
})
