import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { routerKey } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import ContestEditorView from './ContestEditorView.vue'

afterEach(() => vi.unstubAllGlobals())

const user = {
  id: 4,
  username: 'manager',
  email: 'manager@example.test',
  display_name: 'Contest Manager',
  role: 'contest_manager',
}
const contest = {
  id: 31,
  owner_user_id: 4,
  name: 'Summer Sprint',
  slug: 'summer-sprint',
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

function ok(payload: unknown) {
  return new Response(JSON.stringify(payload), { status: 200 })
}
function mountEditor(contestId?: string) {
  return mount(ContestEditorView, {
    props: contestId ? { contestId } : {},
    global: {
      provide: { [routerKey]: { push: vi.fn() } },
      stubs: {
        RouterLink: { template: '<a :href="to"><slot /></a>', props: ['to'] },
      },
    },
  })
}

describe('ContestEditorView', () => {
  it('creates a contest on the dedicated create page with UTC cutoff settings', async () => {
    const bodies: Array<Record<string, unknown>> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.endsWith('/contests') && init?.method === 'POST') {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>
          bodies.push(body)
          return ok({ id: 55, ...body, status: 'draft', owner_user_id: 4 })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountEditor()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Create a contest')
    await wrapper.get('input').setValue('Spring Sprint')
    const inputs = wrapper.findAll('input')
    await inputs[1]?.setValue('spring-sprint')
    const datetimes = wrapper.findAll('input[type="datetime-local"]')
    await datetimes[0]?.setValue('2026-05-01T00:00')
    await datetimes[1]?.setValue('2026-05-01T06:00')
    await datetimes[2]?.setValue('2026-05-08T00:00')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(bodies[0]?.starts_at).toBe('2026-05-01T00:00:00Z')
    expect(bodies[0]?.log_submission_cutoff_at).toBe('2026-05-08T00:00:00Z')
    expect(bodies[0]?.auto_recalculate_on_upload).toBe(true)
    expect(wrapper.get('[role="status"]').text()).toContain(
      'created as a draft',
    )
    await expectAccessible(wrapper.element)
  })

  it('loads and saves a contest on the dedicated edit page', async () => {
    const updates: Array<Record<string, unknown>> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.endsWith('/contests/31') && init?.method === 'GET')
          return ok(contest)
        if (path.endsWith('/contests/31') && init?.method === 'PUT') {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>
          updates.push(body)
          return ok({ ...contest, ...body })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountEditor('31')
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Edit contest')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe(
      'Summer Sprint',
    )
    expect(wrapper.text()).toContain('Contest periodicity')
    await wrapper.get('textarea').setValue('Updated _description_')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(updates[0]?.description).toBe('Updated _description_')
    expect(updates[0]?.periodicity).toEqual({
      frequency: 'annual_date',
      month: 7,
      day: 4,
    })
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Contest details saved',
    )
    await expectAccessible(wrapper.element)
  })

  it('confirms series deletion with the canonical name from a generated edition', async () => {
    const edition = {
      ...contest,
      name: 'Annual Sprint — 2027-05-08',
      slug: 'annual-sprint-9-20270508',
      series_id: 9,
      series_name: 'Annual Sprint',
      is_series_anchor: false,
      series_edition_count: 4,
      series_cutoff_offset_seconds: 172800,
      series_automatic_window_days: 90,
    }
    const routerPush = vi.fn()
    const deleteRequests: Array<Record<string, unknown>> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.endsWith('/contests/31') && init?.method === 'GET')
          return ok(edition)
        if (path.endsWith('/contests/series/9/exceptions'))
          return ok({ items: [] })
        if (path.endsWith('/contests/series/9') && init?.method === 'DELETE') {
          deleteRequests.push(JSON.parse(String(init.body)))
          return new Response(null, { status: 204 })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mount(ContestEditorView, {
      props: { contestId: '31' },
      global: {
        provide: { [routerKey]: { push: routerPush } },
        stubs: {
          RouterLink: { template: '<a :href="to"><slot /></a>', props: ['to'] },
        },
      },
    })
    await flushPromises()

    await wrapper.get('button.danger-button').trigger('click')
    const confirmationInput = document.body.querySelector<HTMLInputElement>(
      '[data-confirmation-input]',
    )!
    confirmationInput.value = 'Annual Sprint'
    confirmationInput.dispatchEvent(new Event('input', { bubbles: true }))
    await wrapper.vm.$nextTick()
    await document.body
      .querySelector<HTMLButtonElement>('button[type="submit"]')!
      .click()
    await flushPromises()

    expect(deleteRequests).toEqual([{ confirm_name: 'Annual Sprint' }])
    expect(routerPush).toHaveBeenCalledWith('/manage/contests')
  })

  it('creates a recurring series with a relative cutoff and rolling window', async () => {
    const submissions: Array<Record<string, unknown>> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.endsWith('/contests') && init?.method === 'POST') {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>
          submissions.push(body)
          return ok({ id: 55, ...body, status: 'draft', owner_user_id: 4 })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountEditor()
    await flushPromises()
    const inputs = wrapper.findAll('input')
    await inputs[0]?.setValue('Annual Sprint')
    await inputs[1]?.setValue('annual-sprint')
    const datetimes = wrapper.findAll('input[type="datetime-local"]')
    await datetimes[0]?.setValue('2026-05-01T12:00')
    await datetimes[1]?.setValue('2026-05-01T18:00')
    const selects = wrapper.findAll('.schedule-controls select')
    await selects[0]?.setValue('annual_date')
    const recurringSelects = wrapper.findAll('.schedule-controls select')
    await recurringSelects[1]?.setValue(5)
    await wrapper
      .findAll('label')
      .find((label) =>
        label.text().includes('Default time after each edition ends'),
      )!
      .get('input[type="number"]')
      .setValue('2')
    const cutoffUnitSelect = wrapper
      .findAll('.schedule-controls select')
      .find((select) => select.text().includes('hours'))
    await cutoffUnitSelect?.setValue('days')
    const autoCreateToggle = wrapper
      .findAll('label.checkbox-field')
      .find((label) => label.text().includes('Automatically create future'))
    await autoCreateToggle!.get('input').setValue(true)
    await wrapper.findAll('input[type="number"]').at(-1)?.setValue('90')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(submissions[0]?.periodicity).toEqual({
      frequency: 'annual_date',
      month: 5,
      day: 1,
    })
    expect(submissions[0]?.cutoff_offset_seconds).toBe(172800)
    expect(submissions[0]?.cutoff_is_override).toBe(false)
    expect(submissions[0]?.log_submission_cutoff_at).toBe(
      '2026-05-03T18:00:00.000Z',
    )
    expect(submissions[0]?.automatic_window_days).toBe(90)
  })

  it('saves multiple months and weekdays for an nth-weekday schedule', async () => {
    const submissions: Array<Record<string, unknown>> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.endsWith('/contests') && init?.method === 'POST') {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>
          submissions.push(body)
          return ok({ id: 55, ...body, status: 'draft', owner_user_id: 4 })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountEditor()
    await flushPromises()
    const inputs = wrapper.findAll('input')
    await inputs[0]?.setValue('Nth Weekday Sprint')
    await inputs[1]?.setValue('nth-weekday-sprint')
    const datetimes = wrapper.findAll('input[type="datetime-local"]')
    await datetimes[0]?.setValue('2026-01-02T08:00')
    await datetimes[1]?.setValue('2026-01-02T09:00')
    await datetimes[2]?.setValue('2026-01-09T09:00')
    const scheduleSelects = wrapper.findAll('.schedule-controls select')
    await scheduleSelects[0]?.setValue('nth_weekday')

    const monthChecks = wrapper
      .findAll('fieldset.schedule-selection')
      .at(0)!
      .findAll('input')
    await monthChecks[2]?.setValue(true)
    const weekdayChecks = wrapper
      .findAll('fieldset.schedule-selection')
      .at(1)!
      .findAll('input')
    await weekdayChecks[0]?.setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(submissions[0]?.periodicity).toEqual({
      frequency: 'nth_weekday',
      month: [1, 3],
      weekday: [0, 5],
      occurrence: 1,
    })
  })

  it('loads multiple recurrence selections and saves nth full-weekend months', async () => {
    const updates: Array<Record<string, unknown>> = []
    const recurringContest = {
      ...contest,
      starts_at: '2026-01-03T08:00:00Z',
      ends_at: '2026-01-03T09:00:00Z',
      periodicity: {
        frequency: 'nth_full_weekend',
        month: [1, 5],
        occurrence: 1,
      },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/auth/me')) return ok(user)
        if (path.endsWith('/contests/31') && init?.method === 'GET')
          return ok(recurringContest)
        if (path.endsWith('/contests/31') && init?.method === 'PUT') {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>
          updates.push(body)
          return ok({ ...recurringContest, ...body })
        }
        throw new Error(`Unexpected request: ${path}`)
      }),
    )
    const wrapper = mountEditor('31')
    await flushPromises()
    const monthChecks = wrapper.findAll('fieldset.schedule-selection input')
    expect((monthChecks[0]?.element as HTMLInputElement).checked).toBe(true)
    expect((monthChecks[4]?.element as HTMLInputElement).checked).toBe(true)
    expect((monthChecks[1]?.element as HTMLInputElement).checked).toBe(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(updates[0]?.periodicity).toEqual({
      frequency: 'nth_full_weekend',
      month: [1, 5],
      occurrence: 1,
    })
  })
})
