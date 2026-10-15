import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
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

    await wrapper.get('input').setValue('Spring Sprint')
    const textInputs = wrapper.findAll('input')
    await textInputs[1]?.setValue('spring-sprint')
    const dateInputs = wrapper.findAll('input[type="datetime-local"]')
    await dateInputs[0]?.setValue('2026-05-01T00:00')
    await dateInputs[1]?.setValue('2026-05-01T06:00')
    await dateInputs[2]?.setValue('2026-05-08T00:00')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('.contest-form').trigger('submit')
    await flushPromises()

    expect(saved).toHaveLength(1)
    expect(saved[0]?.starts_at).toBe(new Date('2026-05-01T00:00').toISOString())
    expect(saved[0]?.ends_at).toBe(new Date('2026-05-01T06:00').toISOString())
    expect(saved[0]?.log_submission_cutoff_at).toBe(
      new Date('2026-05-08T00:00').toISOString(),
    )
    expect(saved[0]?.auto_recalculate_on_upload).toBe(true)
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Contest created as a draft',
    )
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
    const contest = {
      id: 12,
      owner_user_id: 4,
      name: 'Field Day Sprint',
      slug: 'field-day-sprint',
      description: null,
      starts_at: '2026-06-20T00:00:00Z',
      ends_at: '2026-06-20T06:00:00Z',
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
          expect(JSON.parse(String(init.body))).toEqual({
            ruleset_version_id: 21,
          })
          return ok({ ...contest, ruleset_version_id: 21 })
        }
        if (path.includes('/contests')) {
          return ok({
            items: [{ ...contest, ruleset_version_id: 21 }],
            meta: { page: 1, page_size: 100, total: 1, pages: 1 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountManager()
    await flushPromises()

    await wrapper.get('select').setValue('21')
    await wrapper.get('.ruleset-row button').trigger('click')
    await flushPromises()

    expect(
      fetchMock.mock.calls.some(([path]) =>
        String(path).endsWith('/contests/12/ruleset'),
      ),
    ).toBe(true)
    expect(wrapper.text()).toContain('Ruleset assigned to Field Day Sprint')
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
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe(
      'Summer QSO Party',
    )
    await wrapper.get('input').setValue('Updated QSO Party')
    await wrapper.get('.contest-form').trigger('submit')
    await flushPromises()

    expect(updateBodies[0]?.name).toBe('Updated QSO Party')
    expect(wrapper.text()).toContain('Updated QSO Party')
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Contest details saved',
    )
  })
})

const editableContest = {
  id: 31,
  owner_user_id: 4,
  name: 'Summer QSO Party',
  slug: 'summer-qso-party',
  description: 'Annual contest',
  starts_at: '2026-07-04T12:00:00Z',
  ends_at: '2026-07-04T18:00:00Z',
  log_submission_cutoff_at: '2026-07-11T12:00:00Z',
  status: 'draft',
  auto_recalculate_on_upload: false,
  ruleset_version_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
