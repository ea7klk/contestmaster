import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import ContestManagerView from './ContestManagerView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const manager = {
  id: 4,
  username: 'manager',
  email: 'manager@example.test',
  display_name: 'Contest Manager',
  role: 'contest_manager',
}
const contest = (id: number, name: string, status = 'draft') => ({
  id,
  owner_user_id: 4,
  name,
  slug: name.toLowerCase().replaceAll(' ', '-'),
  description: null,
  starts_at: '2026-07-04T12:00:00Z',
  ends_at: '2026-07-04T18:00:00Z',
  periodicity: null,
  log_submission_cutoff_at: '2026-07-11T12:00:00Z',
  status,
  auto_recalculate_on_upload: false,
  ruleset_version_id: status === 'draft' ? null : 21,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
})
const meta = { page: 1, page_size: 20, total: 0, pages: 0 }

function ok(payload: unknown) {
  return new Response(JSON.stringify(payload), { status: 200 })
}

function rulesets(items: unknown[] = []) {
  return {
    items,
    meta: { page: 1, page_size: 100, total: items.length, pages: 1 },
  }
}

function mountManager() {
  return mount(ContestManagerView, {
    global: {
      stubs: {
        RouterLink: { template: '<a :href="to"><slot /></a>', props: ['to'] },
      },
    },
  })
}

async function selectContestPackage(element: Element, contents: string) {
  const input = element.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement))
    throw new Error('Import input missing')
  const file = new File([contents], 'contest.json', {
    type: 'application/json',
  })
  Object.defineProperty(file, 'text', { value: async () => contents })
  Object.defineProperty(input, 'files', { configurable: true, value: [file] })
  input.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
}

describe('ContestManagerView listing', () => {
  it('lists and filters paged contests, without embedding the editor form', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/auth/me')) return ok(manager)
      if (path.includes('/rulesets/versions')) return ok(rulesets())
      if (path.includes('/contests?')) {
        const url = new URL(path, 'http://localhost')
        const q = url.searchParams.get('q')
        const items =
          q === 'summer'
            ? [contest(41, 'Summer QSO Party')]
            : [
                contest(41, 'Summer QSO Party'),
                contest(42, 'Winter Sprint', 'open'),
              ]
        return ok({
          items,
          meta: {
            page: Number(url.searchParams.get('page')),
            page_size: 20,
            total: items.length,
            pages: 1,
          },
        })
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await expectAccessible(wrapper.element)

    expect(wrapper.findAll('.contest-card')).toHaveLength(2)
    expect(wrapper.find('.contest-form').exists()).toBe(false)
    expect(wrapper.get('a[href="/manage/contests/new"]').text()).toContain(
      'Create a contest',
    )
    expect(wrapper.get('a[href="/manage/rulesets"]').text()).toContain(
      'Manage rulesets',
    )
    await wrapper.get('#contest-filter').setValue('summer')
    await flushPromises()
    expect(wrapper.findAll('.contest-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Summer QSO Party')
    expect(wrapper.text()).not.toContain('Winter Sprint')
    expect(
      fetchMock.mock.calls.some(([path]) => String(path).includes('q=summer')),
    ).toBe(true)
  })

  it('navigates between contest pages through server pagination', async () => {
    const pages: number[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(manager)
        if (path.includes('/rulesets/versions')) return ok(rulesets())
        if (path.includes('/contests?')) {
          const url = new URL(path, 'http://localhost')
          const page = Number(url.searchParams.get('page'))
          pages.push(page)
          return ok({
            items: [contest(page, `Contest ${page}`)],
            meta: { page, page_size: 20, total: 21, pages: 2 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountManager()
    await flushPromises()
    await wrapper.findAll('.pagination button')[1]?.trigger('click')
    await flushPromises()
    expect(pages).toEqual([1, 2])
    expect(wrapper.text()).toContain('Page 2 of 2')
    expect(wrapper.text()).toContain('Contest 2')
  })

  it('keeps status, ruleset assignment, logs, and result actions in the list', async () => {
    let status = 'draft'
    let assigned = false
    const savedRuleset = {
      id: 21,
      ruleset_key: 'field-day',
      version: '2026',
      source_url: null,
      source_edition: null,
      rule_type_keys: ['categories'],
      created_by_user_id: 4,
      created_at: '2026-01-01T00:00:00Z',
      can_delete: true,
    }
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(manager)
        if (path.includes('/rulesets/versions'))
          return ok(rulesets([savedRuleset]))
        if (path.endsWith('/contests/12/ruleset') && init?.method === 'PUT') {
          assigned = true
          return ok({
            ...contest(12, 'Field Day Sprint'),
            ruleset_version_id: 21,
          })
        }
        if (path.endsWith('/contests/12/status') && init?.method === 'PUT') {
          status = 'open'
          return ok({ ...contest(12, 'Field Day Sprint', status) })
        }
        if (path.includes('/contests?'))
          return ok({
            items: [
              {
                ...contest(12, 'Field Day Sprint', status),
                ruleset_version_id: assigned ? 21 : null,
              },
            ],
            meta: { ...meta, total: 1, pages: 1 },
          })
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await wrapper.get('.ruleset-row select').setValue('21')
    await wrapper.get('.ruleset-row button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Ruleset assigned to Field Day Sprint')
    expect(
      wrapper.get('a[href="/manage/contests/12/results"]').text(),
    ).toContain('Generate and publish results')
    expect(
      wrapper.get('a[href="/manage/contests/12/entries"]').text(),
    ).toContain('Submitted logs')
    expect(wrapper.get('a[href="/manage/rulesets/21/edit"]').text()).toContain(
      'Edit ruleset',
    )
    await wrapper.get('.contest-card button.primary-button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(
      'Field Day Sprint is now open to the public.',
    )
  })

  it('imports a contest package from the listing and displays the created draft', async () => {
    const packageDraft = {
      contest: {
        name: 'Imported Rally',
        slug: 'imported-rally',
        description: null,
        starts_at: '2026-06-20T00:00:00Z',
        ends_at: '2026-06-20T06:00:00Z',
        log_submission_cutoff_at: '2026-06-27T00:00:00Z',
        auto_recalculate_on_upload: false,
      },
      ruleset: {
        schema_version: 2,
        ruleset_key: 'imported-rally',
        version: '2026',
        rules: [],
      },
    }
    let imported = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(manager)
        if (path.includes('/rulesets/versions')) return ok(rulesets())
        if (path.endsWith('/contests/import') && init?.method === 'POST') {
          expect(JSON.parse(String(init.body))).toEqual(packageDraft)
          imported = true
          return ok({
            contest: contest(81, 'Imported Rally'),
            ruleset_version_id: 21,
          })
        }
        if (path.includes('/contests?')) {
          const items = imported ? [contest(81, 'Imported Rally')] : []
          return ok({
            items,
            meta: { ...meta, total: items.length, pages: items.length ? 1 : 0 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountManager()
    await flushPromises()
    await selectContestPackage(wrapper.element, JSON.stringify(packageDraft))
    expect(wrapper.text()).toContain('Imported Rally')
    expect(wrapper.text()).toContain('Imported Imported Rally as a draft')
  })

  it('keeps delete confirmation and cascade deletion on the listing page', async () => {
    let exists = true
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(manager)
        if (path.includes('/rulesets/versions')) return ok(rulesets())
        if (path.endsWith('/contests/49') && init?.method === 'DELETE') {
          expect(JSON.parse(String(init.body))).toEqual({
            confirm_slug: 'delete-me',
          })
          exists = false
          return new Response(null, { status: 204 })
        }
        if (path.includes('/contests?')) {
          const items = exists ? [contest(49, 'Delete Me')] : []
          return ok({
            items,
            meta: { ...meta, total: items.length, pages: items.length ? 1 : 0 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    vi.spyOn(window, 'prompt').mockReturnValue('delete-me')
    const wrapper = mountManager()
    await flushPromises()
    await wrapper.get('.danger-button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.contest-card')).toHaveLength(0)
    expect(wrapper.text()).toContain('contest data were deleted')
  })

  it('shows an accessible sign-in prompt when unauthenticated', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { message: 'Authentication is required.' },
            }),
            { status: 401 },
          ),
      ),
    )
    const wrapper = mountManager()
    await flushPromises()
    expect(wrapper.text()).toContain('Sign-in required')
  })

  it('shows distinct empty and API error states for the contest list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(manager)
        if (path.includes('/rulesets/versions')) return ok(rulesets())
        return ok({ items: [], meta: { ...meta, pages: 0 } })
      }),
    )
    const empty = mountManager()
    await flushPromises()
    expect(empty.text()).toContain('You have not created a contest yet.')
    empty.unmount()

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(manager)
        if (path.includes('/rulesets/versions')) return ok(rulesets())
        return new Response(
          JSON.stringify({
            error: { message: 'Contest service unavailable.' },
          }),
          { status: 503 },
        )
      }),
    )
    const failed = mountManager()
    await flushPromises()
    expect(failed.get('[role="alert"]').text()).toContain(
      'Contest service unavailable.',
    )
  })
})
