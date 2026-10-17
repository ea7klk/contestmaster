import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expectAccessible } from '../test/a11y'
import LogSubmissionView from './LogSubmissionView.vue'

const responseBody = {
  status: 'accepted',
  replayed: false,
  entry_id: 8,
  entry_key: 'guest-entry',
  receipt_token: 'one-time-entry-token',
  summary: {
    accepted_qsos: 3,
    rejected_qsos: 0,
    error_count: 0,
    warning_count: 1,
  },
  errors: [],
  warnings: [
    { line: 8, code: 'unknown_header', message: 'Header was preserved.' },
  ],
}

afterEach(() => vi.unstubAllGlobals())
const pendingUploadCompletions: Array<() => void> = []

describe('LogSubmissionView', () => {
  it('filters file types per contest and clears a file when the contest changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              items: [
                {
                  id: 1,
                  name: 'Digital Sprint',
                  slug: 'digital-sprint',
                  cutoff_at: '2026-12-01T00:00:00Z',
                  accepted_formats: ['adif'],
                },
                {
                  id: 2,
                  name: 'Phone Sprint',
                  slug: 'phone-sprint',
                  cutoff_at: '2026-12-01T00:00:00Z',
                  accepted_formats: ['cabrillo'],
                },
              ],
            }),
            { status: 200 },
          ),
      ),
    )
    const wrapper = mount(LogSubmissionView, {
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()
    await wrapper.get('#upload-contest').setValue('digital-sprint')

    const input = wrapper.get<HTMLInputElement>('#log-file')
    expect(input.attributes('accept')).toBe('.adi,.adif')
    expect(wrapper.get('label[for="log-file"]').text()).toBe('ADI/ADIF file')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['<EOR>'], 'entry.adif', { type: 'text/plain' })],
    })
    await input.trigger('change')
    expect(
      wrapper.get('button[type="submit"]').attributes('disabled'),
    ).toBeUndefined()

    await wrapper.get('#upload-contest').setValue('phone-sprint')
    expect(input.attributes('accept')).toBe('.log,.cbr,.cabrillo,.txt')
    expect(wrapper.get('label[for="log-file"]').text()).toBe('Cabrillo file')
    expect(
      wrapper.get('button[type="submit"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('shows progress, import summary, warnings, and the entry receipt token', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            items: [
              {
                id: 1,
                name: 'Winter Sprint',
                slug: 'winter-sprint',
                cutoff_at: '2026-12-01T00:00:00Z',
                accepted_formats: ['adif', 'cabrillo'],
              },
            ],
          }),
          { status: 200 },
        ),
    )
    vi.stubGlobal('fetch', fetchMock)

    pendingUploadCompletions.length = 0
    class FakeRequest {
      upload = { onprogress: null as ((event: ProgressEvent) => void) | null }
      status = 201
      responseText = JSON.stringify(responseBody)
      headers = new Map<string, string>()
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      open() {}
      setRequestHeader(name: string, value: string) {
        this.headers.set(name, value)
      }
      send(body: FormData) {
        expect(body.get('file')).toBeInstanceOf(File)
        pendingUploadCompletions.push(() => this.onload?.())
        this.upload.onprogress?.({
          lengthComputable: true,
          loaded: 50,
          total: 100,
        } as ProgressEvent)
      }
    }
    vi.stubGlobal('XMLHttpRequest', FakeRequest)

    const wrapper = mount(LogSubmissionView, {
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()
    await wrapper.get('#upload-contest').setValue('winter-sprint')
    expect(wrapper.get('label[for="log-file"]').text()).toBe(
      'Cabrillo or ADI/ADIF file',
    )
    expect(wrapper.get('#log-file').attributes('accept')).toContain('.adi')
    const input = wrapper.get<HTMLInputElement>('#log-file')
    const file = new File(['START-OF-LOG'], 'entry.log', { type: 'text/plain' })
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [file],
    })
    await input.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('.upload-progress').text()).toContain('50%')
    pendingUploadCompletions[0]?.()
    await flushPromises()

    expect(wrapper.get('[aria-labelledby="result-title"]').text()).toContain(
      '3 contacts accepted',
    )
    expect(wrapper.text()).toContain('one-time-entry-token')
    expect(wrapper.text()).toContain('Header was preserved.')
    await expectAccessible(wrapper.element)
  })

  it('announces line-level parser errors as a rejected log', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              items: [
                {
                  id: 1,
                  name: 'Sprint',
                  slug: 'sprint',
                  accepted_formats: ['cabrillo'],
                },
              ],
            }),
            {
              status: 200,
            },
          ),
      ),
    )
    class RejectedRequest {
      upload = { onprogress: null }
      status = 422
      responseText = JSON.stringify({
        status: 'rejected',
        summary: {
          accepted_qsos: 0,
          rejected_qsos: 1,
          error_count: 1,
          warning_count: 0,
        },
        errors: [
          {
            line: 12,
            code: 'incomplete_qso',
            message: 'QSO record is incomplete.',
          },
        ],
        warnings: [],
      })
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      open() {}
      setRequestHeader() {}
      send() {
        this.onload?.()
      }
    }
    vi.stubGlobal('XMLHttpRequest', RejectedRequest)

    const wrapper = mount(LogSubmissionView, {
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()
    await wrapper.get('#upload-contest').setValue('sprint')
    const input = wrapper.get<HTMLInputElement>('#log-file')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['broken'], 'entry.log', { type: 'text/plain' })],
    })
    await input.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('#result-title').text()).toBe('Log needs correction')
    expect(wrapper.text()).toContain('Line 12: QSO record is incomplete.')
  })

  it('offers independent optional access and result email choices after acceptance', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes('/guest-email')) {
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'guest@example.test',
          entry_access: false,
          result_notifications: true,
        })
        return new Response(
          JSON.stringify({
            status: 'verification_required',
            verified: false,
            verification_email_sent: true,
          }),
          { status: 200 },
        )
      }
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 1,
              name: 'Digital Sprint',
              slug: 'digital-sprint',
              cutoff_at: '2026-12-01T00:00:00Z',
              accepted_formats: ['adif'],
            },
          ],
        }),
        { status: 200 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    class AcceptedAdifRequest {
      upload = { onprogress: null }
      status = 201
      responseText = JSON.stringify({
        ...responseBody,
        guest_email_prompt_required: true,
        guest_email_verification_sent: null,
      })
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      open() {}
      setRequestHeader() {}
      send() {
        this.onload?.()
      }
    }
    vi.stubGlobal('XMLHttpRequest', AcceptedAdifRequest)
    const wrapper = mount(LogSubmissionView, {
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [] })],
      },
    })
    await flushPromises()
    await wrapper.get('#upload-contest').setValue('digital-sprint')
    const input = wrapper.get<HTMLInputElement>('#log-file')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['<EOR>'], 'entry.adi', { type: 'text/plain' })],
    })
    await input.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.findAll('#guest-contact-email')).toHaveLength(1)
    expect(wrapper.text()).toContain('These are separate choices.')
    await wrapper.get('#guest-contact-email').setValue('guest@example.test')
    await wrapper.get('#guest-results-notices').setValue(true)
    const saveEmailChoices = wrapper
      .findAll('button')
      .find((button) => button.text().includes('Save email choices'))
    expect(saveEmailChoices).toBeDefined()
    await saveEmailChoices?.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('A verification link was sent.')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/public/entries/8/guest-email',
      expect.objectContaining({ method: 'POST' }),
    )
    await expectAccessible(wrapper.element)
  })
})
