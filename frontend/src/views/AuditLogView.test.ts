import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import AuditLogView from './AuditLogView.vue'

afterEach(() => vi.unstubAllGlobals())

describe('AuditLogView', () => {
  it('loads and filters the audit feed with accessible controls', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      expect(path).toContain('/admin/audit-events')
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 2,
              occurred_at: '2026-10-18T10:00:00Z',
              actor_user_id: 1,
              actor: 'Admin',
              action: 'score_run.calculated',
              target_type: 'score_run',
              target_id: '55',
              target_name: 'Score run 55',
              reason: null,
              metadata: { status: 'completed', trigger: 'manager' },
              request_id: 'request-55',
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
          retention_days: 90,
          action_options: ['score_run.calculated', 'contest.updated'],
          target_type_options: ['contest', 'score_run'],
        }),
        { status: 200 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AuditLogView, {
      global: { mocks: { $tr: (value: string) => value } },
    })
    await flushPromises()
    await expectAccessible(wrapper.element)
    expect(wrapper.text()).toContain('score_run.calculated')
    expect(wrapper.text()).toContain('request-55')
    expect(wrapper.text()).toContain('Score run 55')
    const actions = wrapper.get('#audit-action')
    expect(actions.element.tagName).toBe('SELECT')
    expect((actions.element as HTMLSelectElement).multiple).toBe(true)
    await actions.setValue(['score_run.calculated', 'contest.updated'])
    await wrapper.get('#audit-target').setValue(['score_run'])
    await wrapper.get('#audit-search').setValue('score')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const requestUrl = new URL(
      String(fetchMock.mock.calls[1][0]),
      'http://localhost',
    )
    expect(requestUrl.searchParams.get('q')).toBe('score')
    expect(requestUrl.searchParams.getAll('action')).toEqual([
      'score_run.calculated',
      'contest.updated',
    ])
    expect(requestUrl.searchParams.getAll('target_type')).toEqual(['score_run'])
  })

  it('shows a clear access error when the API denies access', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              error: { message: 'Global administrator access is required.' },
            }),
            { status: 403 },
          ),
      ),
    )
    const wrapper = mount(AuditLogView, {
      global: { mocks: { $tr: (value: string) => value } },
    })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain(
      'Global administrator',
    )
  })
})
