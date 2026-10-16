import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import { createMemoryHistory, createRouter } from 'vue-router'
import ContestResultsManagerView from './ContestResultsManagerView.vue'

afterEach(() => vi.unstubAllGlobals())

function reviewPayload(unresolved = true) {
  return {
    contest_id: 4,
    contest_slug: 'spring-sprint',
    status: 'closed',
    publication_policy: { include_checklog: false },
    items: [
      {
        entry_id: 7,
        entry_status: 'accepted',
        is_late: false,
        revision_id: 9,
        revision_number: 1,
        score_run_id: 15,
        score_run_status: 'completed',
        callsign: 'EA7AAA',
        category_values: { operator: 'single' },
        result_status: 'scored',
        included_by_default: true,
        score: 88,
        explanation: {},
      },
    ],
    unresolved: unresolved
      ? [
          {
            entry_id: 7,
            revision_id: 9,
            score_run_id: 15,
            status: 'qso_review',
            qso_ids: [22],
          },
        ]
      : [],
    unresolved_count: unresolved ? 1 : 0,
  }
}

describe('ContestResultsManagerView', () => {
  it('runs scoring, submits manual QSO decisions, and publishes selected runs', async () => {
    const calls: Array<{ path: string; method: string; body?: string }> = []
    let hasUnresolved = true
    let finishGeneration: ((response: Response) => void) | undefined
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ path, method, body: init?.body?.toString() })
      if (path.endsWith('/results/review')) {
        return new Response(JSON.stringify(reviewPayload(hasUnresolved)), { status: 200 })
      }
      if (path.endsWith('/results/generate')) {
        return new Promise<Response>((resolve) => {
          finishGeneration = resolve
        }).then(
          (response) => response,
        )
      }
      if (path.endsWith('/qsos/22/decisions')) {
        hasUnresolved = false
        return new Response(JSON.stringify({ status: 'not_credited' }), { status: 201 })
      }
      if (path.endsWith('/results/publish')) {
        return new Response(
          JSON.stringify({ id: 2, contest_id: 4, publication_number: 1, source_digest: 'b'.repeat(64), entry_count: 1, withheld_count: 0, published_at: '2026-04-02T00:00:00Z', status: 'published' }),
          { status: 201 },
        )
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: () => 'retry-safe-phase8-key' })
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/manage/contests', component: { template: '<div />' } }] })
    const wrapper = mount(ContestResultsManagerView, {
      props: { contestId: '4' },
      global: { plugins: [router] },
    })
    await flushPromises()
    await expectAccessible(wrapper.element)

    expect(wrapper.text()).toContain('Unresolved items (1)')
    await wrapper.get('#reason-22').setValue('Verified against the other submitted log.')
    await wrapper.get('.qso-review').trigger('submit')
    await flushPromises()
    expect(calls.some((call) => call.path.endsWith('/qsos/22/decisions'))).toBe(true)
    const decision = JSON.parse(calls.find((call) => call.path.endsWith('/qsos/22/decisions'))?.body ?? '{}') as Record<string, unknown>
    expect(decision.reason).toBe('Verified against the other submitted log.')

    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()
    expect(wrapper.get('progress').attributes('aria-label')).toBe(
      'Calculating contest results',
    )
    expect(wrapper.text()).toContain('This may take a while')
    await expectAccessible(wrapper.element)
    finishGeneration?.(
      new Response(
        JSON.stringify({ contest_id: 4, score_runs: [{ id: 15, entry_id: 7, status: 'completed' }], unresolved_count: 1, unresolved: [] }),
        { status: 202 },
      ),
    )
    await flushPromises()
    expect(wrapper.find('progress').exists()).toBe(false)
    expect(calls.some((call) => call.path.endsWith('/results/generate'))).toBe(true)
    await wrapper.get('button.secondary-button').trigger('click')
    await flushPromises()
    const publication = JSON.parse(calls.find((call) => call.path.endsWith('/results/publish'))?.body ?? '{}') as { score_run_ids: number[] }
    expect(publication.score_run_ids).toEqual([15])
    expect(wrapper.text()).toContain('Publication 1 is live')
  })

  it('clears the progress bar and reports a generation failure', async () => {
    let finishGeneration: ((response: Response) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/results/review')) {
          return new Response(JSON.stringify(reviewPayload(false)), { status: 200 })
        }
        if (path.endsWith('/results/generate')) {
          return new Promise<Response>((resolve) => {
            finishGeneration = resolve
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    vi.stubGlobal('crypto', { randomUUID: () => 'retry-safe-phase8-key' })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/manage/contests', component: { template: '<div />' } }],
    })
    const wrapper = mount(ContestResultsManagerView, {
      props: { contestId: '4' },
      global: { plugins: [router] },
    })
    await flushPromises()

    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('progress').exists()).toBe(true)
    finishGeneration?.(
      new Response(
        JSON.stringify({ error: { message: 'Scoring could not finish.' } }),
        { status: 500 },
      ),
    )
    await flushPromises()

    expect(wrapper.find('progress').exists()).toBe(false)
    expect(wrapper.text()).toContain('Scoring could not finish.')
  })
})
