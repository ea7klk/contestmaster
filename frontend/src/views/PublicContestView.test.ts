import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import { setLocale } from '../i18n'
import PublicContestView from './PublicContestView.vue'

const details = {
  id: 8,
  name: 'Autumn Test',
  slug: 'autumn-test',
  description: 'A public contest.',
  starts_at: '2026-10-20T00:00:00Z',
  ends_at: '2026-10-20T06:00:00Z',
  periodicity: null,
  log_submission_cutoff_at: '2026-10-21T00:00:00Z',
  status: 'open',
  ruleset: {
    schema_version: 2,
    ruleset_key: 'autumn-test',
    version: '2026',
    rules: [
      {
        id: 'eligibility',
        rule: {
          kind: 'eligibility',
          allowed_bands: ['20m', '40m'],
          allowed_modes: ['CW'],
          reject_self_contacts: true,
          reject_out_of_period: true,
          reject_missing_required_exchange: true,
        },
      },
      {
        id: 'points',
        rule: { kind: 'points', fact: 'fixed', fixed_points: 2 },
      },
    ],
  },
}

describe('PublicContestView', () => {
  it('updates generated summaries when the selected language changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(details), { status: 200 })),
    )
    const wrapper = mount(PublicContestView, {
      props: { slug: 'autumn-test' },
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('Eligible contacts may use')

    await setLocale('de', undefined)
    await nextTick()
    expect(wrapper.text()).toContain('Berechtigte Kontakte können')

    await setLocale('en', undefined)
    await nextTick()
    expect(wrapper.text()).toContain('Eligible contacts may use')
  })

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
    expect(wrapper.get('#ruleset-overview-title').text()).toBe(
      'Contest rules at a glance',
    )
    expect(wrapper.text()).toContain(
      'automatically generated from the ruleset and may be imprecise',
    )
    expect(wrapper.text()).toContain(
      'The English version of this description remains authoritative.',
    )
    expect(wrapper.text()).toContain('bands 20m and 40m')
    expect(wrapper.text()).toContain('modes CW')
    expect(wrapper.text()).toContain('Each eligible contact is worth 2 points.')
    expect(wrapper.get('a.primary-button').attributes('href')).toBe(
      '/submit-log?contest=autumn-test',
    )
    await expectAccessible(wrapper.element)
  })

  it('shows format-specific required fields and the contest name required by Cabrillo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...details,
              ruleset: {
                ...details.ruleset,
                rules: [
                  ...details.ruleset.rules,
                  {
                    id: 'categories',
                    rule: {
                      kind: 'categories',
                      dimensions: [
                        {
                          key: 'power',
                          label: 'Power class',
                          choices: [
                            { key: 'qrp', label: 'QRP' },
                            { key: 'low', label: 'Low Power' },
                            { key: 'high', label: 'High Power' },
                          ],
                        },
                      ],
                    },
                  },
                  {
                    id: 'format',
                    rule: { kind: 'format_mapping', format: 'cabrillo' },
                  },
                ],
              },
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

    expect(wrapper.text()).toContain('Required Cabrillo fields')
    expect(wrapper.text()).toContain(
      'CONTEST must match “Autumn Test” or “autumn-test”',
    )
    expect(wrapper.text()).toContain('Allowed band values: 20m and 40m')
    expect(wrapper.text()).toContain('Allowed mode values: CW')
    expect(wrapper.text()).toContain('QRP: Maximum transmit output: 5 W.')
    expect(wrapper.text()).toContain(
      'Low Power: Maximum transmit output: 100 W.',
    )
    expect(wrapper.text()).toContain(
      'High Power: Maximum transmit output: up to the applicable legal limit.',
    )
    expect(
      wrapper.text().match(/Unless contest rules specify otherwise/g),
    ).toHaveLength(1)
    const detailLists = wrapper.findAll(
      '.ruleset-overview ul.summary-detail-list',
    )
    expect(detailLists).toHaveLength(2)
    expect(detailLists[0]?.findAll('li')).toHaveLength(1)
    expect(detailLists[1]?.findAll('li').length).toBeGreaterThan(8)
  })

  it('renders manager Markdown above the generated summary and strips unsafe HTML', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              ...details,
              description:
                'A **public** contest.\n\n<script>alert(1)</script><img src=x onerror=alert(1)> [unsafe](javascript:alert(1))',
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

    const description = wrapper.get('.contest-description')
    expect(description.find('strong').text()).toBe('public')
    expect(description.find('script').exists()).toBe(false)
    expect(description.find('img').exists()).toBe(false)
    expect(description.find('a').exists()).toBe(false)
    expect(
      wrapper.element
        .querySelector('.contest-description')
        ?.compareDocumentPosition(
          wrapper.element.querySelector('.ruleset-overview') as Node,
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    await expectAccessible(wrapper.element)
  })

  it('omits an empty contest description', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ ...details, description: '  ' }), {
            status: 200,
          }),
      ),
    )
    const wrapper = mount(PublicContestView, {
      props: { slug: 'autumn-test' },
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()
    expect(wrapper.find('.contest-description').exists()).toBe(false)
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
