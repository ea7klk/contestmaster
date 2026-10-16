import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import RulesetManagerView from './RulesetManagerView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const user = {
  id: 4,
  username: 'manager',
  email: 'manager@example.test',
  display_name: 'Manager',
  role: 'contest_manager',
}
const saved = (id: number, key: string) => ({
  id,
  ruleset_key: key,
  version: '2026',
  source_url: null,
  source_edition: '2026 edition',
  rule_type_keys: ['categories', 'score_formula'],
  created_by_user_id: 4,
  created_at: '2026-01-01T00:00:00Z',
  can_delete: true,
})
const ok = (payload: unknown) =>
  new Response(JSON.stringify(payload), { status: 200 })

function mountList() {
  return mount(RulesetManagerView, {
    global: {
      stubs: {
        RouterLink: { template: '<a :href="to"><slot /></a>', props: ['to'] },
      },
    },
  })
}

describe('RulesetManagerView', () => {
  it('shows a paged listing and applies server-side filtering', async () => {
    const paths: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        paths.push(path)
        if (path.endsWith('/auth/me')) return ok(user)
        const url = new URL(path, 'http://localhost')
        if (url.pathname.endsWith('/rulesets/versions')) {
          const filtered = url.searchParams.get('q') === 'field'
          const page = Number(url.searchParams.get('page'))
          return ok({
            items: filtered
              ? [saved(2, 'field-day')]
              : [saved(1, `rules-${page}`)],
            meta: {
              page,
              page_size: 20,
              total: filtered ? 1 : 21,
              pages: filtered ? 1 : 2,
            },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountList()
    await flushPromises()
    await expectAccessible(wrapper.element)
    expect(wrapper.get('h1').text()).toBe('Rulesets')
    expect(wrapper.findAll('.row')).toHaveLength(1)
    expect(wrapper.text()).toContain('Page 1 of 2')
    expect(wrapper.get('a[href="/manage/rulesets/new"]').text()).toContain(
      'Create ruleset',
    )
    expect(
      wrapper.get('a[href="/manage/rulesets/new#import-ruleset"]').text(),
    ).toContain('Import ruleset')
    await wrapper.findAll('.pagination button')[1]?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Page 2 of 2')
    expect(wrapper.text()).toContain('rules-2')
    await wrapper.get('input[type="search"]').setValue('field')
    await flushPromises()
    expect(wrapper.text()).toContain('field-day · version 2026')
    expect(wrapper.text()).not.toContain('rules-2 · version 2026')
    expect(paths.some((path) => path.includes('q=field'))).toBe(true)
  })

  it('starts a new ruleset version from the selected saved version and deletes unused versions', async () => {
    let current = saved(8, 'unused-rules')
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.includes('/rulesets/versions') && init?.method === 'DELETE') {
          expect(JSON.parse(String(init.body))).toEqual({
            confirm_identity: 'unused-rules@2026',
          })
          current = null as unknown as typeof current
          return new Response(null, { status: 204 })
        }
        if (path.includes('/rulesets/versions'))
          return ok({
            items: current ? [current] : [],
            meta: {
              page: 1,
              page_size: 20,
              total: current ? 1 : 0,
              pages: current ? 1 : 0,
            },
          })
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'prompt').mockReturnValue('unused-rules@2026')
    const wrapper = mountList()
    await flushPromises()
    expect(wrapper.get('a[href="/manage/rulesets/8/edit"]').text()).toContain(
      'Create version from this ruleset',
    )
    await wrapper.get('.danger-button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Deleted unused ruleset unused-rules@2026')
    expect(wrapper.text()).toContain('No saved ruleset versions')
  })

  it('exports a saved ruleset version as JSON and reports export failures', async () => {
    const configuration = {
      schema_version: 2,
      ruleset_key: 'field-day',
      version: '2026',
      rules: [],
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/auth/me')) return ok(user)
      if (path.includes('/rulesets/versions?'))
        return ok({
          items: [saved(12, 'field-day')],
          meta: { page: 1, page_size: 20, total: 1, pages: 1 },
        })
      if (path.endsWith('/rulesets/versions/12'))
        return ok({ id: 12, configuration })
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const createObjectURL = vi.fn(() => 'blob:test-ruleset')
    const revokeObjectURL = vi.fn()
    const NativeURL = URL
    class TestURL extends NativeURL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    }
    vi.stubGlobal('URL', TestURL)
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    const wrapper = mountList()
    await flushPromises()
    await wrapper.get('.row-actions button').trigger('click')
    await flushPromises()
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).endsWith('/rulesets/versions/12'),
      ),
    ).toBe(true)
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-ruleset')
    expect(wrapper.text()).toContain('Exported field-day version 2026.')

    wrapper.unmount()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.includes('/rulesets/versions?'))
          return ok({
            items: [saved(12, 'field-day')],
            meta: { page: 1, page_size: 20, total: 1, pages: 1 },
          })
        return new Response(
          JSON.stringify({ error: { message: 'Export data unavailable.' } }),
          { status: 503 },
        )
      }),
    )
    const failed = mountList()
    await flushPromises()
    await failed.get('.row-actions button').trigger('click')
    await flushPromises()
    expect(failed.get('[role="alert"]').text()).toContain(
      'Export data unavailable.',
    )
  })

  it('shows empty and API error states for the ruleset listing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        return ok({
          items: [],
          meta: { page: 1, page_size: 20, total: 0, pages: 0 },
        })
      }),
    )
    const empty = mountList()
    await flushPromises()
    expect(empty.text()).toContain(
      'No saved ruleset versions are available yet.',
    )
    empty.unmount()

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        return new Response(
          JSON.stringify({
            error: { message: 'Ruleset service unavailable.' },
          }),
          { status: 503 },
        )
      }),
    )
    const failed = mountList()
    await flushPromises()
    expect(failed.get('[role="alert"]').text()).toContain(
      'Ruleset service unavailable.',
    )
  })
})
