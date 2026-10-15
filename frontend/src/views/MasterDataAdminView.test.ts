import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import MasterDataAdminView from './MasterDataAdminView.vue'

afterEach(() => vi.unstubAllGlobals())

const candidate = {
  id: 12,
  dataset_key: 'cty',
  status: 'candidate',
  is_current: false,
  valid_from: '2026-01-01T00:00:00Z',
  valid_to: null,
  activated_at: null,
  created_at: '2026-01-01T00:00:00Z',
  provenance: {
    id: 20,
    dataset_key: 'cty',
    source_key: 'big-cty',
    source_name: 'Big CTY',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:01:00Z',
    retrieved_at: '2026-01-01T00:00:30Z',
    source_url: 'https://example.test/cty.dat',
    source_release: '2026-01',
    checksum: 'a'.repeat(64),
    parser_version: '1',
    status: 'succeeded',
    change_detected: true,
    record_counts: { prefixes: 1 },
    error_summary: null,
  },
  references: { contest: 0, score_run: 0, qso_resolution: 0 },
  can_activate: true,
  can_delete: true,
}

async function mountView(role: 'global_administrator' | 'contest_manager') {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path.endsWith('/auth/me')) {
        return new Response(
          JSON.stringify({ id: 1, role, display_name: 'User' }),
          { status: 200 },
        )
      }
      if (path.endsWith('/admin/master-data/versions')) {
        return new Response(JSON.stringify({ items: [candidate] }), {
          status: 200,
        })
      }
      if (path.endsWith('/admin/master-data/sync-runs')) {
        return new Response(
          JSON.stringify({
            items: [
              {
                ...candidate.provenance,
                change_detected: false,
                status: 'succeeded',
                error_summary: null,
              },
            ],
          }),
          { status: 200 },
        )
      }
      expect(path).toContain('/admin/master-data/versions/12/')
      expect(init?.method).toMatch(/POST|DELETE/)
      return new Response(JSON.stringify({ id: 12, status: 'active' }), {
        status: 200,
      })
    },
  )
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(MasterDataAdminView)
  await flushPromises()
  return { wrapper, fetchMock }
}

describe('MasterDataAdminView', () => {
  it('loads provenance and no-change sync history for global administrators', async () => {
    const { wrapper, fetchMock } = await mountView('global_administrator')
    await expectAccessible(wrapper.element)

    expect(wrapper.text()).toContain('Big CTY')
    expect(wrapper.text()).toContain('2026-01')
    expect(wrapper.text()).toContain('No content change')
    expect(wrapper.findAll('button').map((button) => button.text())).toContain(
      'Activate',
    )
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('never requests master-data history for a contest manager', async () => {
    const { wrapper, fetchMock } = await mountView('contest_manager')

    expect(wrapper.get('[role="alert"]').text()).toContain(
      'Global administrator',
    )
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('requires confirmation and sends activation through the shared API client', async () => {
    const confirm = vi.fn(() => true)
    const prompt = vi.fn(() => 'validated feed')
    vi.stubGlobal('confirm', confirm)
    vi.stubGlobal('prompt', prompt)
    const { wrapper, fetchMock } = await mountView('global_administrator')

    const activateButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Activate')
    expect(activateButton).toBeDefined()
    await activateButton!.trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledOnce()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).includes(
            '/admin/master-data/versions/12/activate?audit_reason=',
          ) && init?.method === 'POST',
      ),
    ).toBe(true)
  })

  it('confirms deletion before calling the protected delete API', async () => {
    const confirm = vi.fn(() => true)
    const prompt = vi.fn(() => 'obsolete snapshot')
    vi.stubGlobal('confirm', confirm)
    vi.stubGlobal('prompt', prompt)
    const { wrapper, fetchMock } = await mountView('global_administrator')

    const deleteButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Delete')
    expect(deleteButton).toBeDefined()
    await deleteButton!.trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledOnce()
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).includes(
            '/admin/master-data/versions/12?audit_reason=',
          ) && init?.method === 'DELETE',
      ),
    ).toBe(true)
  })
})
