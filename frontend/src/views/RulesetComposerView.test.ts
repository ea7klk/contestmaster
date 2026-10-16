import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import RulesetComposerView from './RulesetComposerView.vue'

const requiredRules = [
  'schedule',
  'submission',
  'categories',
  'exchange',
  'eligibility',
  'duplicates',
  'points',
  'score_formula',
  'format_mapping',
]

function catalogResponse() {
  return {
    rule_types: requiredRules.map((key) => ({
      key,
      label: key,
      description: `${key} rule`,
      execution: 'automatic',
      required: true,
      schema: {
        type: 'object',
        properties: { kind: { const: key, type: 'string' } },
        required: ['kind'],
      },
    })),
  }
}

function operatingCatalogResponse() {
  return { items: [] }
}

afterEach(() => vi.unstubAllGlobals())

describe('RulesetComposerView', () => {
  it.each([
    ['/rulesets/bands', 'band'],
    ['/rulesets/modes', 'mode'],
  ])(
    'identifies when the %s eligibility catalog fails to load',
    async (path, kind) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: RequestInfo | URL) => {
          const url = String(input)
          if (url.endsWith('/rulesets/catalog'))
            return new Response(JSON.stringify(catalogResponse()), {
              status: 200,
            })
          if (url.endsWith(path))
            return new Response(
              JSON.stringify({
                error: { message: 'Catalog service is unavailable.' },
              }),
              { status: 503 },
            )
          if (
            url.endsWith('/rulesets/bands') ||
            url.endsWith('/rulesets/modes')
          )
            return new Response(JSON.stringify(operatingCatalogResponse()), {
              status: 200,
            })
          throw new Error(`Unexpected request ${url}`)
        }),
      )
      const wrapper = mount(RulesetComposerView)
      await flushPromises()

      expect(wrapper.get('[role="alert"]').text()).toContain(
        `The ${kind} catalog could not be loaded: Catalog service is unavailable.`,
      )
    },
  )

  it('places each eligibility toggle above its matching catalog choices', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/rulesets/catalog'))
          return new Response(JSON.stringify(catalogResponse()), {
            status: 200,
          })
        if (
          path.endsWith('/rulesets/bands') ||
          path.endsWith('/rulesets/modes')
        )
          return new Response(JSON.stringify(operatingCatalogResponse()), {
            status: 200,
          })
        throw new Error(`Unexpected request ${path}`)
      }),
    )
    const wrapper = mount(RulesetComposerView)
    await flushPromises()

    for (const [toggleText, legendText] of [
      ['Configure allowed bands', 'Eligible bands'],
      ['Configure allowed modes', 'Allowed modes'],
    ]) {
      const toggle = wrapper
        .findAll('label')
        .find((label) => label.text().includes(toggleText))
      expect(toggle).toBeDefined()
      await toggle!.get('input').setValue(true)
      await flushPromises()
      const legend = wrapper
        .findAll('legend')
        .find((item) => item.text() === legendText)
      expect(legend).toBeDefined()
      expect(
        toggle!.element.compareDocumentPosition(legend!.element) & 4,
      ).toBeTruthy()
    }
  })

  it('explains UTC scheduling and the configurable rule sections', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).endsWith('/rulesets/catalog'))
          return new Response(JSON.stringify(catalogResponse()), {
            status: 200,
          })
        if (
          String(input).endsWith('/rulesets/bands') ||
          String(input).endsWith('/rulesets/modes')
        )
          return new Response(JSON.stringify(operatingCatalogResponse()), {
            status: 200,
          })
        throw new Error(`Unexpected request ${String(input)}`)
      }),
    )
    const wrapper = mount(RulesetComposerView)
    await flushPromises()
    await expectAccessible(wrapper.element)
    const text = wrapper.text()
    expect(text).toContain('All contest times use UTC')
    expect(text).toContain('Daylight-saving clock folds')
    expect(text).toContain('classification axes')
    expect(text).toContain('Exchange schema')
    expect(text).toContain('combines the worked callsign')
    expect(text).toContain('non-negative integers')
    expect(text).toContain('apply steps from top to bottom')
    expect(text).toContain('Unknown input fields can be preserved')
  })

  it('loads required rule types and sends the configured draft for validation', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith('/rulesets/catalog')) {
          return new Response(JSON.stringify(catalogResponse()), {
            status: 200,
          })
        }
        if (
          String(input).endsWith('/rulesets/bands') ||
          String(input).endsWith('/rulesets/modes')
        ) {
          return new Response(JSON.stringify(operatingCatalogResponse()), {
            status: 200,
          })
        }
        expect(String(input)).toMatch(/\/rulesets\/validate$/)
        expect(init?.method).toBe('POST')
        const draft = JSON.parse(String(init?.body))
        expect(draft.schema_version).toBe(1)
        expect(draft.ruleset_key).toBe('my-contest')
        expect(
          draft.rules.map((item: { rule: { kind: string } }) => item.rule.kind),
        ).toEqual(requiredRules)
        expect(
          draft.rules.find(
            (item: { rule: { kind: string } }) =>
              item.rule.kind === 'eligibility',
          ).rule.eligible_if,
        ).toEqual({
          kind: 'compare',
          fact: 'qso.entity',
          operator: 'eq',
          value: 'K',
        })
        return new Response(
          JSON.stringify({
            valid: true,
            ruleset_key: 'my-contest',
            version: '1',
            rule_types: requiredRules,
            summary: 'my-contest version 1.',
            worked_score_example: {
              final_score: 120,
              steps: [{ operation: 'start', result: 120 }],
            },
          }),
          { status: 200 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(RulesetComposerView)
    await flushPromises()
    expect(wrapper.findAll('.rule-card')).toHaveLength(requiredRules.length)
    await wrapper
      .findAll('.rule-card')[4]
      .get('.condition-toggle input')
      .setValue(true)

    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(wrapper.get('[role="status"]').text()).toContain('Ruleset is valid')
    expect(wrapper.text()).toContain('Worked integer score example')
  })

  it('shows API validation errors without replacing the draft with a success result', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/rulesets/catalog')) {
        return new Response(JSON.stringify(catalogResponse()), { status: 200 })
      }
      if (
        String(input).endsWith('/rulesets/bands') ||
        String(input).endsWith('/rulesets/modes')
      ) {
        return new Response(JSON.stringify(operatingCatalogResponse()), {
          status: 200,
        })
      }
      return new Response(
        JSON.stringify({
          error: {
            message: 'Ruleset configuration is invalid.',
            details: [
              {
                location: ['rules', 0],
                message: 'Schedule is required.',
                type: 'invalid',
              },
            ],
          },
        }),
        { status: 422 },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(RulesetComposerView)
    await flushPromises()
    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain(
      'configuration is invalid',
    )
    expect(wrapper.get('.error-list').text()).toContain('Schedule is required')
    expect(wrapper.find('.validation-panel').exists()).toBe(false)
  })

  it('persists a validated immutable ruleset version', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith('/rulesets/catalog')) {
          return new Response(JSON.stringify(catalogResponse()), {
            status: 200,
          })
        }
        if (
          String(input).endsWith('/rulesets/bands') ||
          String(input).endsWith('/rulesets/modes')
        ) {
          return new Response(JSON.stringify(operatingCatalogResponse()), {
            status: 200,
          })
        }
        if (String(input).endsWith('/rulesets/validate')) {
          return new Response(
            JSON.stringify({
              valid: true,
              ruleset_key: 'my-contest',
              version: '1',
              rule_types: requiredRules,
              summary: 'my-contest version 1.',
              worked_score_example: { final_score: 120, steps: [] },
            }),
            { status: 200 },
          )
        }
        expect(String(input)).toMatch(/\/rulesets\/versions$/)
        expect(init?.method).toBe('POST')
        const saved = JSON.parse(String(init?.body))
        expect(saved.ruleset_key).toBe('my-contest')
        return new Response(
          JSON.stringify({
            id: 3,
            ruleset_key: 'my-contest',
            version: '1',
            rule_type_keys: requiredRules,
            created: true,
            created_at: '2026-01-01T00:00:00Z',
          }),
          { status: 201 },
        )
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(RulesetComposerView)
    await flushPromises()
    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()
    await wrapper.findAll('button.primary-button')[1]?.trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(5)
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Saved my-contest version 1',
    )
  })

  it('loads a saved version for editing and saves a separate version', async () => {
    const originalConfiguration = {
      schema_version: 1,
      ruleset_key: 'field-day',
      version: '2026',
      rules: requiredRules.map((kind) => ({ id: kind, rule: { kind } })),
    }
    const savedDrafts: Record<string, unknown>[] = []
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input)
        if (path.endsWith('/rulesets/catalog'))
          return new Response(JSON.stringify(catalogResponse()), {
            status: 200,
          })
        if (
          path.endsWith('/rulesets/bands') ||
          path.endsWith('/rulesets/modes')
        )
          return new Response(JSON.stringify(operatingCatalogResponse()), {
            status: 200,
          })
        if (path.endsWith('/rulesets/versions/21'))
          return new Response(
            JSON.stringify({ id: 21, configuration: originalConfiguration }),
            { status: 200 },
          )
        if (path.endsWith('/rulesets/validate'))
          return new Response(
            JSON.stringify({
              valid: true,
              ruleset_key: 'field-day',
              version: '2026-revised',
              rule_types: requiredRules,
              summary: 'field-day version 2026-revised.',
              worked_score_example: { final_score: 120, steps: [] },
            }),
            { status: 200 },
          )
        if (path.endsWith('/rulesets/versions') && init?.method === 'POST') {
          const draft = JSON.parse(String(init.body)) as Record<string, unknown>
          savedDrafts.push(draft)
          return new Response(
            JSON.stringify({
              id: 22,
              ruleset_key: 'field-day',
              version: '2026-revised',
              rule_type_keys: requiredRules,
              created: true,
              created_at: '2026-01-01T00:00:00Z',
            }),
            { status: 201 },
          )
        }
        throw new Error(`Unexpected request ${path}`)
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(RulesetComposerView, {
      props: { editVersionId: '21' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Editing field-day version 2026')
    expect(
      (wrapper.get('.metadata-panel input').element as HTMLInputElement).value,
    ).toBe('field-day')
    await wrapper.findAll('button.primary-button')[0]?.trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toContain(
      'Enter a new version identifier',
    )
    expect(
      fetchMock.mock.calls.some(([path]) =>
        String(path).endsWith('/rulesets/validate'),
      ),
    ).toBe(false)
    await wrapper.findAll('.metadata-panel input')[1]?.setValue('2026-revised')
    await wrapper.findAll('button.primary-button')[0]?.trigger('click')
    await flushPromises()
    await wrapper.findAll('button.primary-button')[1]?.trigger('click')
    await flushPromises()

    expect(savedDrafts).toHaveLength(1)
    expect(savedDrafts[0]?.ruleset_key).toBe('field-day')
    expect(savedDrafts[0]?.version).toBe('2026-revised')
    expect(wrapper.get('[role="status"]').text()).toContain(
      'field-day version 2026 remains unchanged',
    )
  })
})
