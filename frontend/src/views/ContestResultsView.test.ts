import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ContestResultsView from './ContestResultsView.vue'

afterEach(() => vi.unstubAllGlobals())

function resultsPage() {
  return {
    contest: {
      id: 1,
      name: 'Spring Sprint',
      slug: 'spring-sprint',
      description: null,
      starts_at: '2026-04-01T00:00:00Z',
      ends_at: '2026-04-01T06:00:00Z',
      status: 'published',
      publication: {
        number: 2,
        published_at: '2026-04-02T00:00:00Z',
        source_digest: 'a'.repeat(64),
        entry_count: 1,
        withheld_count: 0,
      },
    },
    items: [
      {
        id: 9,
        callsign: 'EA7AAA',
        category_values: { operator: 'single', band: '20M', mode: 'CW' },
        status: 'scored',
        score: 64,
        points: 32,
        multiplier_count: 2,
        bonus_points: 1,
        penalty_points: 0,
        qso_count: 8,
        credited_qso_count: 8,
        placement: 1,
        explanation: {
          format_version: 1,
          points: 32,
          multipliers: 2,
          bonus_points: 1,
          penalty_points: 0,
          score: 64,
          qso_count: 8,
          credited_qso_count: 8,
          summary: 'Integer score produced by the published contest ruleset.',
        },
      },
    ],
    filters: {
      categories: [{ key: 'operator', values: ['single'] }],
      bands: ['20M'],
      modes: ['CW'],
      statuses: ['scored'],
    },
    meta: { page: 1, page_size: 50, total: 1, pages: 1 },
  }
}

describe('ContestResultsView', () => {
  it('renders published totals, safe explanations, filters, exports, and pages', async () => {
    const paths: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        paths.push(String(input))
        return new Response(JSON.stringify(resultsPage()), { status: 200 })
      }),
    )
    const wrapper = mount(ContestResultsView, { props: { slug: 'spring-sprint' } })
    await flushPromises()

    expect(wrapper.text()).toContain('Spring Sprint')
    expect(wrapper.text()).toContain('EA7AAA')
    expect(wrapper.text()).toContain('64')
    expect(wrapper.text()).toContain('QSO points')
    expect(wrapper.get('a[href$="?format=json"]').text()).toContain('JSON v1')
    expect(wrapper.get('a[href$="?format=csv"]').text()).toContain('CSV v1')
    expect(wrapper.findAll('select')).toHaveLength(4)

    await wrapper.findAll('select')[0]?.setValue('operator')
    await flushPromises()
    expect(wrapper.findAll('select')).toHaveLength(5)
    await wrapper.findAll('select')[1]?.setValue('single')
    await flushPromises()
    expect(paths.some((path) => path.includes('category=operator'))).toBe(true)
    expect(paths.some((path) => path.includes('value=single'))).toBe(true)
    expect(wrapper.find('table').exists()).toBe(true)
  })

  it('renders a server error without leaving a stale result list visible', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({ error: { message: 'Contest not found.' } }),
          { status: 404 },
        ),
      ),
    )
    const wrapper = mount(ContestResultsView, { props: { slug: 'private-contest' } })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Contest not found.')
    expect(wrapper.find('table').exists()).toBe(false)
  })
})
