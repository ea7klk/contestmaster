import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import ContestEntriesView from './ContestEntriesView.vue'

afterEach(() => vi.unstubAllGlobals())

function ok(payload: unknown) {
  return new Response(JSON.stringify(payload), { status: 200 })
}

const contest = {
  id: 7,
  owner_user_id: 4,
  name: 'Spring Test Sprint',
  slug: 'spring-test-sprint',
  description: null,
  starts_at: '2026-04-01T00:00:00Z',
  ends_at: '2026-04-01T06:00:00Z',
  periodicity: null,
  log_submission_cutoff_at: '2026-04-08T00:00:00Z',
  status: 'closed',
  auto_recalculate_on_upload: false,
  ruleset_version_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const summary = {
  entry_id: 22,
  entry_key: 'k1test-entry',
  callsign: 'K1TEST',
  status: 'received',
  is_late: false,
  category_values: { operator: 'single' },
  submitted_at: '2026-04-02T00:00:00Z',
  revision_id: 34,
  revision_number: 2,
  input_format: 'cabrillo',
  original_filename: 'k1test.log',
  qso_count: 1,
}

const logDetails = {
  entry: { ...summary, revision_count: 2 },
  revisions: [
    {
      id: 34,
      revision_number: 2,
      input_format: 'cabrillo',
      original_filename: 'k1test.log',
      byte_size: 512,
      submitted_at: '2026-04-02T00:00:00Z',
      received_at: '2026-04-02T00:00:00Z',
      qso_count: 1,
    },
    {
      id: 30,
      revision_number: 1,
      input_format: 'cabrillo',
      original_filename: 'k1test-first.log',
      byte_size: 400,
      submitted_at: '2026-04-01T00:00:00Z',
      received_at: '2026-04-01T00:00:00Z',
      qso_count: 1,
    },
  ],
  contacts: [
    {
      id: 91,
      source_line_number: 6,
      occurred_at: '2026-04-01T01:15:00Z',
      callsign: 'K2ONE',
      band: '20m',
      mode: 'CW',
      exchange_sent: { serial: '001' },
      exchange_received: { serial: '014' },
    },
  ],
  meta: { page: 1, page_size: 50, total: 1, pages: 1 },
}

describe('ContestEntriesView', () => {
  it('lists submitted logs and opens their QSO details', async () => {
    const requested: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        requested.push(path)
        if (path.endsWith('/contests/7')) return ok(contest)
        if (path.includes('/contests/7/entries?')) {
          return ok({
            items: [summary],
            meta: { page: 1, page_size: 50, total: 1, pages: 1 },
          })
        }
        if (path.includes('/contests/7/entries/22?')) return ok(logDetails)
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/manage/contests/:contestId/entries/:entryId?',
          component: ContestEntriesView,
        },
      ],
    })
    await router.push('/manage/contests/7/entries')
    await router.isReady()
    const wrapper = mount(ContestEntriesView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('Spring Test Sprint')
    expect(wrapper.text()).toContain('K1TEST')
    await expectAccessible(wrapper.element)

    await router.push('/manage/contests/7/entries/22')
    await flushPromises()
    expect(wrapper.text()).toContain('K2ONE')
    expect(wrapper.text()).toContain('Exchange sent')
    expect(wrapper.text()).toContain('serial: 001')
    expect(wrapper.text()).toContain('Revision 1')
    expect(requested.some((path) => path.includes('/entries/22?'))).toBe(true)
    await expectAccessible(wrapper.element)
  })

  it('shows a useful empty state when a contest has no submitted logs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/contests/7')) return ok(contest)
        if (path.includes('/contests/7/entries?')) {
          return ok({
            items: [],
            meta: { page: 1, page_size: 50, total: 0, pages: 0 },
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/manage/contests/:contestId/entries/:entryId?',
          component: ContestEntriesView,
        },
      ],
    })
    await router.push('/manage/contests/7/entries')
    const wrapper = mount(ContestEntriesView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.text()).toContain('No logs have been submitted')
    await expectAccessible(wrapper.element)
  })
})
