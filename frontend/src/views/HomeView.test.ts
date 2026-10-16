import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import HomeView from './HomeView.vue'
import { expectAccessible } from '../test/a11y'

afterEach(() => vi.unstubAllGlobals())

const contest = {
  id: 3,
  name: 'Spring Sprint',
  slug: 'spring-sprint',
  description: 'Six hours on the air.',
  starts_at: '2026-04-01T00:00:00Z',
  ends_at: '2026-04-01T06:00:00Z',
  periodicity: null,
  status: 'published',
  log_submission_cutoff_at: '2026-04-02T00:00:00Z',
}

const upcomingContest = {
  ...contest,
  id: 8,
  name: 'Autumn Test',
  slug: 'autumn-test',
  starts_at: '2027-10-16T00:00:00Z',
  ends_at: '2027-10-16T06:00:00Z',
  periodicity: null,
  log_submission_cutoff_at: '2027-10-17T00:00:00Z',
  status: 'open',
}

function response(items: unknown[]) {
  return new Response(
    JSON.stringify({
      items,
      meta: { page: 1, page_size: 50, total: items.length, pages: 1 },
      as_of: new Date().toISOString(),
    }),
    { status: 200 },
  )
}

function mountHome() {
  const router = createRouter({ history: createMemoryHistory(), routes: [] })
  return mount(HomeView, { global: { plugins: [router] } })
}

describe('HomeView public contest activity', () => {
  it('shows public upcoming contests with UTC times and a contest details link', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        response(String(input).includes('/upcoming') ? [upcomingContest] : []),
      ),
    )
    const wrapper = mountHome()
    await flushPromises()

    expect(wrapper.get('#upcoming-contests-title').text()).toBe(
      'Upcoming contests',
    )
    expect(wrapper.text()).toContain('Autumn Test')
    expect(wrapper.text()).toContain('Upcoming')
    expect(wrapper.text()).toContain('16 Oct 2027, 00:00 UTC')
    expect(
      wrapper.get('.contest-feed-card .results-link').attributes('href'),
    ).toBe('/contests/autumn-test')
    await expectAccessible(wrapper.element)
  })

  it('keeps upcoming loading, empty, and error states separate from published results', async () => {
    let finishUpcoming: ((value: Response) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        if (String(input).includes('/upcoming')) {
          return new Promise<Response>((resolve) => {
            finishUpcoming = resolve
          })
        }
        return Promise.resolve(response([contest]))
      }),
    )
    const loadingWrapper = mountHome()
    await flushPromises()
    expect(
      loadingWrapper.get('.upcoming-contests [role="status"]').text(),
    ).toContain('Loading upcoming contests')
    expect(loadingWrapper.text()).toContain('Spring Sprint')

    finishUpcoming?.(response([]))
    await flushPromises()
    expect(loadingWrapper.text()).toContain(
      'No contests are open or in progress right now. Contest managers can open a draft after assigning a valid ruleset.',
    )
    loadingWrapper.unmount()

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/upcoming')) {
          return new Response(
            JSON.stringify({
              error: { message: 'Upcoming service is unavailable.' },
            }),
            { status: 503 },
          )
        }
        return response([contest])
      }),
    )
    const errorWrapper = mountHome()
    await flushPromises()
    expect(errorWrapper.get('.upcoming-contests [role="alert"]').text()).toBe(
      'Upcoming service is unavailable.',
    )
    expect(errorWrapper.text()).toContain('Spring Sprint')
    errorWrapper.unmount()
  })

  it('shows published contest dates in UTC and links to standings and log submission', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        response(String(input).includes('/upcoming') ? [] : [contest]),
      ),
    )
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    const wrapper = mount(HomeView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe(
      'Find a contest. Make your next contact.',
    )
    expect(wrapper.get('.published-badge').text()).toBe('Results published')
    expect(wrapper.text()).toContain('01 Apr 2026, 00:00 UTC')
    expect(wrapper.text()).toContain('01 Apr 2026, 06:00 UTC')
    expect(wrapper.get('.results-link').attributes('href')).toBe(
      '/contests/spring-sprint/results',
    )
    expect(wrapper.get('.hero-upload').attributes('href')).toBe('/submit-log')
    await expectAccessible(wrapper.element)
  })

  it('filters available public contests by name or description', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        response(
          String(input).includes('/upcoming')
            ? []
            : [
                contest,
                {
                  ...contest,
                  id: 4,
                  name: 'Winter Rally',
                  slug: 'winter-rally',
                  description: 'Digital modes.',
                },
              ],
        ),
      ),
    )
    const wrapper = mountHome()
    await flushPromises()

    await wrapper.get('#contest-search').setValue('digital modes')

    expect(wrapper.text()).toContain('Winter Rally')
    expect(wrapper.text()).not.toContain('Spring Sprint')
    expect(wrapper.text()).toContain('Showing 1 of 2 published contests.')
  })

  it('shows explicit loading, empty, unmatched, and error states', async () => {
    const pending: Array<(value: Response) => void> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            pending.push(resolve)
          }),
      ),
    )
    const loadingWrapper = mountHome()
    expect(
      loadingWrapper.get('.published-contests [role="status"]').text(),
    ).toContain('Loading published contests')

    pending.forEach((resolve) => resolve(response([])))
    await flushPromises()
    expect(loadingWrapper.text()).toContain(
      'No contest results have been published yet.',
    )
    loadingWrapper.unmount()

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => response([contest])),
    )
    const unmatchedWrapper = mountHome()
    await flushPromises()
    await unmatchedWrapper.get('#contest-search').setValue('not found')
    expect(unmatchedWrapper.text()).toContain(
      'No published contests match “not found”',
    )
    unmatchedWrapper.unmount()

    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { message: 'Contest service is unavailable.' },
            }),
            { status: 503 },
          ),
      ),
    )
    const errorWrapper = mountHome()
    await flushPromises()
    expect(errorWrapper.get('[role="alert"]').text()).toBe(
      'Contest service is unavailable.',
    )
  })
})
