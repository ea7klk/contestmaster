import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import ContestManagerView from './ContestManagerView.vue'

afterEach(() => vi.unstubAllGlobals())

function ok(payload: unknown) {
  return new Response(JSON.stringify(payload), { status: 200 })
}

function managerUser() {
  return {
    id: 4,
    username: 'manager',
    email: 'manager@example.test',
    display_name: 'Contest Manager',
    role: 'contest_manager',
  }
}

function mountManager() {
  return mount(ContestManagerView, {
    global: {
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

async function selectFile(element: Element, file: File) {
  const fileInput = element.querySelector('input[type="file"]')
  if (!(fileInput instanceof HTMLInputElement))
    throw new Error('File input missing')
  Object.defineProperty(fileInput, 'files', {
    configurable: true,
    value: [file],
  })
  fileInput.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
}

function jsonFile(contents: string, name: string) {
  const file = new File([contents], name, { type: 'application/json' })
  Object.defineProperty(file, 'text', {
    value: async () => contents,
  })
  return file
}

describe('ContestManagerView', () => {
  it('creates a contest with separate cutoff and automatic recalculation settings', async () => {
    const saved: Record<string, unknown>[] = []
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.includes('/contests') && init?.method === 'POST') {
          const payload = JSON.parse(String(init.body)) as Record<
            string,
            unknown
          >
          saved.push(payload)
          return ok({ id: 5, ...payload, status: 'draft', owner_user_id: 4 })
        }
        if (
          path.endsWith(
            '/contests?page=1&page_size=100&sort=starts_at&order=desc',
          )
        ) {
          return ok({
            items: [],
            meta: { page: 1, page_size: 100, total: 0, pages: 0 },
          })
        }
        if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await expectAccessible(wrapper.element)

    await wrapper.get('.contest-form input').setValue('Spring Sprint')
    const textInputs = wrapper.findAll('.contest-form input')
    await textInputs[1]?.setValue('spring-sprint')
    const dateInputs = wrapper.findAll('input[type="datetime-local"]')
    await dateInputs[0]?.setValue('2026-05-01T00:00')
    await dateInputs[1]?.setValue('2026-05-01T06:00')
    await dateInputs[2]?.setValue('2026-05-08T00:00')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('.contest-form').trigger('submit')
    await flushPromises()

    expect(saved).toHaveLength(1)
    expect(saved[0]?.starts_at).toBe('2026-05-01T00:00:00Z')
    expect(saved[0]?.ends_at).toBe('2026-05-01T06:00:00Z')
    expect(saved[0]?.log_submission_cutoff_at).toBe('2026-05-08T00:00:00Z')
    expect(saved[0]?.periodicity).toBeNull()
    expect(saved[0]?.auto_recalculate_on_upload).toBe(true)
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Contest created as a draft',
    )
  })

  it('shows the contest list before the form with filtering and scroll access', async () => {
    const contests = [
      {
        id: 41,
        owner_user_id: 4,
        name: 'Summer QSO Party',
        slug: 'summer-qso-party',
        description: null,
        starts_at: '2026-07-04T12:00:00Z',
        ends_at: '2026-07-04T18:00:00Z',
        periodicity: null,
        log_submission_cutoff_at: '2026-07-11T12:00:00Z',
        status: 'draft',
        auto_recalculate_on_upload: false,
        ruleset_version_id: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 42,
        owner_user_id: 4,
        name: 'Winter Sprint',
        slug: 'winter-sprint',
        description: null,
        starts_at: '2026-12-04T12:00:00Z',
        ends_at: '2026-12-04T18:00:00Z',
        periodicity: null,
        log_submission_cutoff_at: '2026-12-11T12:00:00Z',
        status: 'open',
        auto_recalculate_on_upload: false,
        ruleset_version_id: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.includes('/contests'))
          return ok({
            items: contests,
            meta: { page: 1, page_size: 100, total: 2, pages: 1 },
          })
        if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountManager()
    await flushPromises()

    const list = wrapper.get('.contest-list')
    const form = wrapper.get('.contest-form')
    expect(list.element.compareDocumentPosition(form.element) & 4).toBe(4)
    expect(wrapper.get('.contest-list-scroll').attributes()).toMatchObject({
      tabindex: '0',
      'aria-label': 'Scrollable contest list',
    })
    expect(wrapper.findAll('.contest-card')).toHaveLength(2)

    await wrapper.get('#contest-filter').setValue('SUMMER-QSO')
    expect(wrapper.findAll('.contest-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Summer QSO Party')
    expect(wrapper.text()).not.toContain('Winter Sprint')

    await wrapper.get('#contest-filter').setValue('open')
    expect(wrapper.findAll('.contest-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Winter Sprint')

    await wrapper.get('#contest-filter').setValue('no-match')
    expect(wrapper.get('[role="status"]').text()).toContain('No contests match')
  })

  it('directs unauthenticated users to staff sign-in', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { message: 'Authentication is required.' },
            }),
            {
              status: 401,
            },
          ),
      ),
    )
    const wrapper = mountManager()
    await flushPromises()

    expect(wrapper.text()).toContain('Sign-in required')
    expect(
      wrapper.findAll('a').find((link) => link.text() === 'Sign in'),
    ).toBeDefined()
  })

  it('assigns a saved ruleset to a draft contest through the authenticated API', async () => {
    let assignedRuleset = false
    const contest = {
      id: 12,
      owner_user_id: 4,
      name: 'Field Day Sprint',
      slug: 'field-day-sprint',
      description: null,
      starts_at: '2026-06-20T00:00:00Z',
      ends_at: '2026-06-20T06:00:00Z',
      periodicity: null,
      log_submission_cutoff_at: '2026-06-27T00:00:00Z',
      status: 'draft',
      auto_recalculate_on_upload: false,
      ruleset_version_id: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.includes('/rulesets/versions')) {
          return ok({
            items: [
              {
                id: 21,
                ruleset_key: 'field-day',
                version: '2026',
                rule_type_keys: ['categories', 'score_formula'],
                source_url: null,
                source_edition: null,
                created_by_user_id: 4,
                created_at: '2026-01-01T00:00:00Z',
              },
            ],
          })
        }
        if (
          path.includes('/contests') &&
          init?.method === 'PUT' &&
          path.endsWith('/ruleset')
        ) {
          assignedRuleset = true
          expect(JSON.parse(String(init.body))).toEqual({
            ruleset_version_id: 21,
          })
          return ok({ ...contest, ruleset_version_id: 21 })
        }
        if (path.includes('/contests')) {
          return ok({
            items: [
              {
                ...contest,
                ruleset_version_id: assignedRuleset ? 21 : null,
              },
            ],
            meta: { page: 1, page_size: 100, total: 1, pages: 1 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    expect(wrapper.text()).not.toContain('Open contest')

    await wrapper.get('.ruleset-row select').setValue('21')
    await wrapper.get('.ruleset-row button').trigger('click')
    await flushPromises()

    expect(
      fetchMock.mock.calls.some(([path]) =>
        String(path).endsWith('/contests/12/ruleset'),
      ),
    ).toBe(true)
    expect(wrapper.text()).toContain('Ruleset assigned to Field Day Sprint')
    expect(wrapper.text()).toContain('Edit ruleset')
    expect(wrapper.text()).toContain('Open contest')
  })

  it('opens a ruleset-ready draft for public discovery', async () => {
    let status = 'draft'
    const statusChanges: Array<{ path: string; status: string }> = []
    const contest = {
      id: 18,
      owner_user_id: 4,
      name: 'Autumn Radio Rally',
      slug: 'autumn-radio-rally',
      description: 'A public weekend contest.',
      starts_at: '2026-11-07T12:00:00Z',
      ends_at: '2026-11-07T18:00:00Z',
      periodicity: null,
      log_submission_cutoff_at: '2026-11-14T12:00:00Z',
      auto_recalculate_on_upload: false,
      ruleset_version_id: 21,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
        if (path.endsWith('/contests/18/status') && init?.method === 'PUT') {
          const payload = JSON.parse(String(init.body)) as { status: string }
          statusChanges.push({ path, status: payload.status })
          status = payload.status
          return ok({ ...contest, status })
        }
        if (path.includes('/contests')) {
          return ok({
            items: [{ ...contest, status }],
            meta: { page: 1, page_size: 100, total: 1, pages: 1 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()

    expect(wrapper.text()).toContain('draft')
    expect(wrapper.text()).toContain('Open contest')
    expect(wrapper.text()).toContain('Opening makes this contest public')
    await wrapper
      .get('.contest-card')
      .get('button.primary-button')
      .trigger('click')
    await flushPromises()

    expect(statusChanges).toEqual([
      { path: '/api/v1/contests/18/status', status: 'open' },
    ])
    expect(wrapper.text()).toContain('open')
    expect(wrapper.text()).toContain(
      'Autumn Radio Rally is now open to the public.',
    )
    await expectAccessible(wrapper.element)
  })

  it('loads an existing contest into the edit form and saves its changed details', async () => {
    let currentName = 'Summer QSO Party'
    const updateBodies: Record<string, unknown>[] = []
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
        if (path.endsWith('/contests/31') && init?.method === 'PUT') {
          const payload = JSON.parse(String(init.body)) as Record<
            string,
            unknown
          >
          updateBodies.push(payload)
          currentName = String(payload.name)
          return ok({ ...editableContest, name: currentName })
        }
        if (path.includes('/contests')) {
          return ok({
            items: [{ ...editableContest, name: currentName }],
            meta: { page: 1, page_size: 100, total: 1, pages: 1 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await wrapper.get('.contest-card .secondary-button').trigger('click')
    expect(wrapper.text()).toContain('Contest description (Markdown)')
    expect(wrapper.text()).toContain('Supports Markdown such as paragraphs')
    expect(
      (wrapper.get('.contest-form input').element as HTMLInputElement).value,
    ).toBe('Summer QSO Party')
    expect(wrapper.text()).toContain('Contest periodicity')
    expect(
      (wrapper.get('.contest-form select').element as HTMLSelectElement).value,
    ).toBe('annual_date')
    const description = wrapper.get('.contest-form textarea')
    expect((description.element as HTMLTextAreaElement).value).toBe(
      'Annual **contest**',
    )
    await description.setValue('Now _updated_')
    await wrapper.get('.contest-form input').setValue('Updated QSO Party')
    await wrapper.get('.contest-form').trigger('submit')
    await flushPromises()

    expect(updateBodies[0]?.name).toBe('Updated QSO Party')
    expect(updateBodies[0]?.description).toBe('Now _updated_')
    expect(updateBodies[0]?.periodicity).toEqual({
      frequency: 'annual_date',
      month: 7,
      day: 4,
    })
    expect(wrapper.text()).toContain('Updated QSO Party')
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Contest details saved',
    )
  })

  it('imports a contest JSON package and refreshes the contest list', async () => {
    const packageDraft = {
      contest: {
        name: 'Imported Field Day',
        slug: 'imported-field-day',
        description: null,
        starts_at: '2026-06-20T00:00:00Z',
        ends_at: '2026-06-20T06:00:00Z',
        log_submission_cutoff_at: '2026-06-27T00:00:00Z',
        auto_recalculate_on_upload: false,
      },
      ruleset: {
        schema_version: 2,
        ruleset_key: 'imported-field-day',
        version: '2026',
        rules: [{ id: 'schedule', rule: { kind: 'schedule' } }],
      },
    }
    const contest = {
      id: 82,
      owner_user_id: 4,
      ...packageDraft.contest,
      status: 'draft',
      ruleset_version_id: 55,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    let imported = false
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.endsWith('/contests/import') && init?.method === 'POST') {
          expect(JSON.parse(String(init.body))).toEqual(packageDraft)
          imported = true
          return ok({ contest, ruleset_version_id: 55 })
        }
        if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
        if (path.includes('/contests')) {
          const items = imported ? [contest] : []
          return ok({
            items,
            meta: { page: 1, page_size: 100, total: items.length, pages: 1 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await expectAccessible(wrapper.element)

    await selectFile(
      wrapper.element,
      jsonFile(JSON.stringify(packageDraft), 'field-day.json'),
    )

    expect(wrapper.text()).toContain('Imported Field Day')
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Imported Imported Field Day as a draft',
    )
    expect(
      fetchMock.mock.calls.some(([path]) =>
        String(path).endsWith('/contests/import'),
      ),
    ).toBe(true)
  })

  it('reports malformed contest package JSON without calling the API', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/auth/me')) return ok(managerUser())
      if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
      if (path.includes('/contests')) {
        return ok({
          items: [],
          meta: { page: 1, page_size: 100, total: 0, pages: 0 },
        })
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await selectFile(wrapper.element, jsonFile('{broken', 'broken.json'))

    expect(wrapper.get('[role="alert"]').text()).toContain('not valid JSON')
    expect(
      fetchMock.mock.calls.some(([path]) =>
        String(path).endsWith('/contests/import'),
      ),
    ).toBe(false)
  })

  it('shows contest import API errors without hiding the draft form', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(managerUser())
        if (path.endsWith('/rulesets/versions')) return ok({ items: [] })
        if (path.endsWith('/contests/import') && init?.method === 'POST') {
          return new Response(
            JSON.stringify({
              error: { message: 'A contest slug is already in use.' },
            }),
            { status: 409 },
          )
        }
        if (path.includes('/contests')) {
          return ok({
            items: [],
            meta: { page: 1, page_size: 100, total: 0, pages: 0 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()
    await selectFile(
      wrapper.element,
      jsonFile(
        JSON.stringify({
          contest: { name: 'Collision' },
          ruleset: { schema_version: 2, ruleset_key: 'collision', rules: [] },
        }),
        'collision.json',
      ),
    )

    expect(wrapper.get('[role="alert"]').text()).toContain(
      'A contest slug is already in use.',
    )
    expect(wrapper.find('.contest-form').exists()).toBe(true)
  })
})

const editableContest = {
  id: 31,
  owner_user_id: 4,
  name: 'Summer QSO Party',
  slug: 'summer-qso-party',
  description: 'Annual **contest**',
  starts_at: '2026-07-04T12:00:00Z',
  ends_at: '2026-07-04T18:00:00Z',
  periodicity: { frequency: 'annual_date', month: 7, day: 4 },
  log_submission_cutoff_at: '2026-07-11T12:00:00Z',
  status: 'draft',
  auto_recalculate_on_upload: false,
  ruleset_version_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
