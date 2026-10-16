import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import OperatingCatalogAdminView from './OperatingCatalogAdminView.vue'

afterEach(() => vi.unstubAllGlobals())

describe('OperatingCatalogAdminView', () => {
  it('loads editable band and mode values for a global administrator', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/auth/me'))
        return new Response(
          JSON.stringify({
            id: 1,
            role: 'global_administrator',
            display_name: 'Admin',
          }),
        )
      if (path.endsWith('/admin/bands'))
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 1,
                kind: 'band',
                key: '60m',
                label: '60 m',
                description: 'notice',
                frequency_range: '5 MHz',
                sort_order: 1,
                is_active: true,
                contest_free: true,
              },
            ],
          }),
        )
      if (path.endsWith('/admin/modes'))
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 2,
                kind: 'mode',
                key: 'FT8',
                label: 'FT8',
                description: 'Digital mode',
                sort_order: 1,
                is_active: true,
              },
            ],
          }),
        )
      throw new Error(`Unexpected request ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(OperatingCatalogAdminView)
    await flushPromises()
    await expectAccessible(wrapper.element)
    expect(wrapper.text()).toContain('60 m')
    expect(wrapper.text()).toContain('FT8')
    expect(wrapper.text()).toContain('Contest-free designation')
    expect(wrapper.text()).toContain('Active in ruleset composer')
    expect(wrapper.findAll('form.catalog-editor-form')).toHaveLength(2)
    expect(wrapper.get('#bands-heading').text()).toBe('Bands')
    expect(wrapper.get('#modes-heading').text()).toBe('Modes')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('does not load configuration for a contest manager', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            id: 2,
            role: 'contest_manager',
            display_name: 'Manager',
          }),
        ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(OperatingCatalogAdminView)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain(
      'Global administrator',
    )
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
