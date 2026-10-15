import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import HomeView from './HomeView.vue'

afterEach(() => vi.unstubAllGlobals())

describe('HomeView public discovery', () => {
  it('lists only published contests and links to their standings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            items: [
              {
                id: 3,
                name: 'Spring Sprint',
                slug: 'spring-sprint',
                description: 'Six hours on the air.',
                starts_at: '2026-04-01T00:00:00Z',
                ends_at: '2026-04-01T06:00:00Z',
                status: 'published',
              },
            ],
            meta: { page: 1, page_size: 50, total: 1, pages: 1 },
          }),
          { status: 200 },
        ),
      ),
    )
    const router = createRouter({ history: createMemoryHistory(), routes: [] })
    const wrapper = mount(HomeView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('Spring Sprint')
    expect(wrapper.get('a').attributes('href')).toBe('/contests/spring-sprint/results')
  })

  it('shows an explicit empty state when no published contest is available', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            items: [],
            meta: { page: 1, page_size: 50, total: 0, pages: 0 },
          }),
          { status: 200 },
        ),
      ),
    )
    const wrapper = mount(HomeView)
    await flushPromises()
    expect(wrapper.text()).toContain('No contest results have been published yet.')
  })
})
