import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import ResourceAdministrators from './ResourceAdministrators.vue'

afterEach(() => vi.unstubAllGlobals())

describe('ResourceAdministrators', () => {
  it('lists assigned administrators and adds an eligible administrator', async () => {
    let assigned = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) {
        return new Response(JSON.stringify({ id: 1, role: 'contest_admin' }), { status: 200 })
      }
      if (init?.method === 'POST') assigned = true
      return new Response(JSON.stringify({
        owner_user_id: 1,
        items: assigned ? [{ user_id: 3, username: 'radio-admin', display_name: 'Radio Admin' }] : [],
        eligible: assigned ? [] : [{ user_id: 3, username: 'radio-admin', display_name: 'Radio Admin' }],
      }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ResourceAdministrators, { props: { resourceKind: 'contest', resourceId: 9 } })
    await flushPromises()
    await expectAccessible(wrapper.element)
    expect(wrapper.text()).toContain('permanent owner')
    await wrapper.get('select').setValue('3')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Radio Admin (radio-admin)')
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true)
    await expectAccessible(wrapper.element)
  })

  it('does not show assignment controls to an assigned administrator', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) {
        return new Response(JSON.stringify({ id: 2, role: 'contest_admin' }), { status: 200 })
      }
      return new Response(JSON.stringify({
        owner_user_id: 1,
        items: [{ user_id: 2, username: 'assigned', display_name: 'Assigned' }],
        eligible: [{ user_id: 3, username: 'other', display_name: 'Other' }],
      }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ResourceAdministrators, { props: { resourceKind: 'ruleset', resourceId: 5 } })
    await flushPromises()
    expect(wrapper.text()).toContain('Assigned (assigned)')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Remove access')
  })
})
