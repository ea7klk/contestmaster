import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import HomeView from './HomeView.vue'
import { expectAccessible } from '../test/a11y'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

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
  starts_at: '2026-10-20T00:00:00Z',
  ends_at: '2026-10-20T06:00:00Z',
  periodicity: null,
  log_submission_cutoff_at: '2026-10-21T00:00:00Z',
  status: 'open',
}

const activeContest = {
  ...contest,
  id: 7,
  name: 'Current Sprint',
  slug: 'current-sprint',
  starts_at: '2026-10-15T20:00:00Z',
  ends_at: '2026-10-16T06:00:00Z',
  periodicity: null,
  log_submission_cutoff_at: '2026-10-17T00:00:00Z',
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
  it('shows active contests before selectable upcoming contests with UTC times', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-16T00:00:00Z'))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        response(
          String(input).includes('/upcoming')
            ? [activeContest, upcomingContest]
            : [],
        ),
      ),
    )
    const wrapper = mountHome()
    await flushPromises()

    expect(wrapper.get('#upcoming-contests-title').text()).toBe(
      'Upcoming contests',
    )
    expect(wrapper.get('#active-contests-title').text()).toBe('Active contests')
    expect(
      wrapper.element
        .querySelector('#active-contests-title')!
        .compareDocumentPosition(
          wrapper.element.querySelector('#upcoming-contests-title')!,
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(wrapper.get('.active-contests').text()).toContain('Current Sprint')
    expect(wrapper.text()).toContain('Autumn Test')
    expect(wrapper.text()).not.toContain('Spring Sprint')
    expect(wrapper.text()).toContain('In progress')
    expect(wrapper.text()).toContain('Upcoming')
    expect(wrapper.text()).toContain('20 Oct 2026, 00:00 UTC')
    expect(
      wrapper.get('.upcoming-contests .results-link').attributes('href'),
    ).toBe('/contests/autumn-test')
    expect(
      (wrapper.get('#upcoming-range').element as HTMLSelectElement).value,
    ).toBe('month')
    await expectAccessible(wrapper.element)
  })

  it('filters upcoming contests to the selected week, month, and three-month window', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-16T00:00:00Z'))
    const nextMonthContest = {
      ...upcomingContest,
      id: 9,
      name: 'November Test',
      slug: 'november-test',
      starts_at: '2026-11-12T00:00:00Z',
    }
    const weekBoundaryContest = {
      ...upcomingContest,
      id: 11,
      name: 'Week Boundary Test',
      slug: 'week-boundary-test',
      starts_at: '2026-10-23T00:00:00Z',
    }
    const monthBoundaryContest = {
      ...upcomingContest,
      id: 12,
      name: 'Month Boundary Test',
      slug: 'month-boundary-test',
      starts_at: '2026-11-16T00:00:00Z',
    }
    const nextQuarterContest = {
      ...upcomingContest,
      id: 10,
      name: 'January Test',
      slug: 'january-test',
      starts_at: '2027-01-10T00:00:00Z',
    }
    const quarterBoundaryContest = {
      ...upcomingContest,
      id: 13,
      name: 'Quarter Boundary Test',
      slug: 'quarter-boundary-test',
      starts_at: '2027-01-16T00:00:00Z',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        response(
          String(input).includes('/upcoming')
            ? [
                activeContest,
                upcomingContest,
                weekBoundaryContest,
                nextMonthContest,
                monthBoundaryContest,
                nextQuarterContest,
                quarterBoundaryContest,
              ]
            : [],
        ),
      ),
    )
    const wrapper = mountHome()
    await flushPromises()

    const upcomingSection = wrapper.get('.upcoming-contests')
    expect(upcomingSection.text()).toContain('Autumn Test')
    expect(upcomingSection.text()).toContain('November Test')
    expect(upcomingSection.text()).toContain('Month Boundary Test')
    expect(upcomingSection.text()).not.toContain('January Test')
    await wrapper.get('#upcoming-range').setValue('week')
    expect(upcomingSection.text()).toContain('Autumn Test')
    expect(upcomingSection.text()).toContain('Week Boundary Test')
    expect(upcomingSection.text()).not.toContain('November Test')
    await wrapper.get('#upcoming-range').setValue('month')
    expect(upcomingSection.text()).toContain('Month Boundary Test')
    expect(upcomingSection.text()).not.toContain('Quarter Boundary Test')
    await wrapper.get('#upcoming-range').setValue('three-months')
    expect(upcomingSection.text()).toContain('January Test')
    expect(upcomingSection.text()).toContain('Quarter Boundary Test')
    expect(upcomingSection.text()).not.toContain('Current Sprint')
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
      'No contests are in progress right now.',
    )
    expect(loadingWrapper.text()).toContain(
      'No contests are scheduled for the next month.',
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
    expect(errorWrapper.get('.active-contests [role="alert"]').text()).toBe(
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
