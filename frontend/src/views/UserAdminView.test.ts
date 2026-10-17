import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import UserAdminView from './UserAdminView.vue'

afterEach(() => vi.unstubAllGlobals())

describe('UserAdminView', () => {
  it('creates a contest administrator and displays privileged and registered participant accounts', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, init })
      if (url.includes('/auth/admin/users')) {
        return new Response(JSON.stringify({
          items: [{ id: 1, username: 'owner', email: 'owner@example.test', display_name: 'Owner', role: 'global_administrator', is_active: true }],
          total: 1, page: 1, page_size: 50,
        }), { status: 200 })
      }
      if (url.includes('/auth/admin/participants')) {
        return new Response(JSON.stringify({ items: [{
          id: 5, display_name: 'Operator', is_active: true, has_password: true,
          callsigns: ['EA7ABC'], emails: [{ email: 'operator@example.test', verified: true, active: true }],
        }], total: 1, page: 1, page_size: 50 }), { status: 200 })
      }
      return new Response(JSON.stringify({ id: 2, username: 'manager', email: 'manager@example.test', display_name: 'Manager', role: 'contest_admin', is_active: true }), { status: 201 })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(UserAdminView)
    await flushPromises()
    await expectAccessible(wrapper.element)
    expect(wrapper.get('.user-admin-card').element).toBeTruthy()
    for (const fieldId of ['new-user-name', 'new-user-email', 'new-user-display', 'new-user-password', 'new-user-role']) {
      expect(wrapper.get(`#${fieldId}`).element.closest('label')).not.toBeNull()
    }
    const passwordChangeOption = wrapper.get('.user-admin-force-password')
    expect(passwordChangeOption.attributes('for')).toBe('new-user-force-password')
    expect(passwordChangeOption.get('input[type="checkbox"]').attributes('id')).toBe('new-user-force-password')
    expect(wrapper.findAll('.user-admin-table-scroll')).toHaveLength(2)
    expect(wrapper.findAll('.user-admin-table colgroup')).toHaveLength(2)
    expect(wrapper.text()).toContain('operator@example.test')
    await wrapper.get('#new-user-name').setValue('manager')
    await wrapper.get('#new-user-email').setValue('manager@example.test')
    await wrapper.get('#new-user-display').setValue('Manager')
    await wrapper.get('#new-user-password').setValue('a sufficiently long test password')
    await wrapper.get('#new-user-force-password').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const createRequest = calls.find(({ init }) => init?.method === 'POST')
    expect(createRequest).toBeDefined()
    expect(JSON.parse(String(createRequest?.init?.body))).toMatchObject({
      must_change_password: true,
    })
    expect(wrapper.get('[role="status"]').text()).toContain('account was created')
    await expectAccessible(wrapper.element)
  })

  it('shows an accessible access-denied state when the API rejects a non-admin', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { message: 'Global administrator access is required.' },
    }), { status: 403 })))
    const wrapper = mount(UserAdminView)
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('administrator access is required')
    await expectAccessible(wrapper.element)
  })
})
