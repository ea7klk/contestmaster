import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectAccessible } from '../test/a11y'
import RulesetComposerView from './RulesetComposerView.vue'

const requiredRules = [
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

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('RulesetComposerView', () => {
  it('keeps the Published rules URL optional marker within its aligned label row', async () => {
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

    const urlLabel = wrapper
      .findAll('.metadata-grid label')
      .find((label) => label.text().includes('Published rules URL'))
    expect(urlLabel).toBeDefined()
    expect(urlLabel!.get('.metadata-field-label').text()).toContain(
      'Published rules URL',
    )
    expect(urlLabel!.get('.metadata-field-label .optional-label').text()).toBe(
      'Optional',
    )
    expect(urlLabel!.get('input[type="url"]')).toBeDefined()
    expect(urlLabel!.get('.field-help').text()).toContain('official rules page')
  })

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

  it('moves legacy event timing out of rulesets during import and exports version 2', async () => {
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
    let downloaded: Blob | undefined
    class TestURL extends URL {
      static createObjectURL(object: Blob | MediaSource) {
        if (object instanceof Blob) downloaded = object
        return 'blob:test-draft'
      }

      static revokeObjectURL() {}
    }
    vi.stubGlobal('URL', TestURL)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    const wrapper = mount(RulesetComposerView)
    await flushPromises()
    const legacyDraft = {
      schema_version: 1,
      ruleset_key: 'legacy-bonus',
      version: '1',
      rules: [
        {
          id: 'schedule',
          rule: {
            kind: 'schedule',
            recurrence: { frequency: 'annual_date', month: 4, day: 2 },
          },
        },
        {
          id: 'submission',
          rule: {
            kind: 'submission',
            late_policy: 'checklog',
            cutoff_mode: 'at_utc',
            cutoff_utc: '2026-04-09T00:00:00Z',
          },
        },
        {
          id: 'completion-bonus',
          rule: {
            kind: 'bonus',
            basis: 'per_entry',
            points: 5,
            evidence_required: true,
            evidence_key: 'proof',
          },
        },
      ],
    }
    const input = wrapper.get('input[type="file"]')
    const file = new File([JSON.stringify(legacyDraft)], 'legacy.json', {
      type: 'application/json',
    })
    Object.defineProperty(file, 'text', {
      value: async () => JSON.stringify(legacyDraft),
    })
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [file],
    })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Configure contest dates, periodicity, and submission cutoff in contest configuration',
    )
    const downloadButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'Download JSON draft')
    expect(downloadButton).toBeDefined()
    await downloadButton!.trigger('click')

    expect(downloaded).toBeDefined()
    const exportedText = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsText(downloaded!)
    })
    const exported = JSON.parse(exportedText)
    expect(exported.schema_version).toBe(2)
    expect(
      exported.rules.map((item: { rule: { kind: string } }) => item.rule.kind),
    ).toEqual(['submission', 'bonus'])
    expect(exported.rules[0].rule).toEqual({
      kind: 'submission',
      late_policy: 'checklog',
    })
    expect(exported.rules[1].rule).toEqual({
      kind: 'bonus',
      basis: 'per_entry',
      points: 5,
      evidence_key: 'proof',
    })
  })

  it('explains reusable ruleset sections without contest schedule controls', async () => {
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
    expect(text).toContain('How to create a ruleset')
    expect(wrapper.findAll('.workflow-guide li')).toHaveLength(4)
    expect(text).toContain('save a new immutable')
    expect(text).toContain('Assign that version to a contest')
    expect(text).toContain('Stable, lowercase identifier')
    expect(text).toContain('new version identifier')
    expect(text).not.toContain('All contest times use UTC')
    expect(text).not.toContain('Daylight-saving clock folds')
    expect(text).not.toContain('Contest schedule')
    expect(text).toContain('classification axes')
    expect(text).toContain('Exchange schema')
    expect(text).toContain('Worked callsign is always part of the identity')
    expect(text).toContain('integer at least zero')
    expect(text).toContain('in the same order as the published formula')
    expect(text).toContain('Unrecognized source fields can be preserved')
    expect(text).toContain(
      'after contacts, multipliers, bonuses, and penalties',
    )
  })

  it('shows useful help for optional multiplier rules when they are added', async () => {
    const response = catalogResponse()
    response.rule_types.push({
      key: 'multiplier',
      label: 'Multiplier',
      description: 'Define a multiplier.',
      execution: 'automatic',
      required: false,
      schema: {
        type: 'object',
        properties: { kind: { const: 'multiplier', type: 'string' } },
        required: ['kind'],
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/rulesets/catalog'))
          return new Response(JSON.stringify(response), { status: 200 })
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
    await wrapper.get('#add-rule-type').setValue('multiplier')
    await wrapper.get('.add-rule-control button').trigger('click')

    const multiplierCard = wrapper
      .findAll('.rule-card')
      .find((card) => card.get('h3').text() === 'Multiplier')
    expect(multiplierCard).toBeDefined()
    expect(multiplierCard!.get('.rule-explanation').text()).toContain(
      'where uniqueness resets',
    )
    expect(multiplierCard!.get('.rule-explanation').text()).toContain(
      'once for the whole contest, per band, per mode',
    )
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
        expect(draft.schema_version).toBe(2)
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
    expect(wrapper.find('#browse-saved-rulesets').exists()).toBe(false)
    expect(wrapper.get('a[href="/manage/rulesets"]').text()).toContain(
      'Back to rulesets',
    )
    expect(wrapper.findAll('.rule-card')).toHaveLength(requiredRules.length)
    const eligibilityRule = wrapper
      .findAll('.rule-card')
      .find((card) => card.get('h3').text() === 'eligibility')
    await eligibilityRule!.get('.condition-toggle input').setValue(true)

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
                location: ['rules[7]', 'qso_columns'],
                message:
                  'Cabrillo QSO columns must explicitly include each required WWROF field exactly once. Field order may follow the contest template; the optional transmitter field must be last.',
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
    expect(wrapper.get('.error-list').text()).toContain('WWROF field')
    expect(wrapper.get('.error-list').text()).toContain('qso_columns')
    expect(wrapper.get('.validation-guidance').text()).toContain('contradiction')
    expect(wrapper.get('.error-list').text()).toContain('rules[7]')
    expect(wrapper.find('.validation-panel').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Save validated ruleset version')
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
      schema_version: 2,
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
        if (path.endsWith('/rulesets/versions') && init?.method === 'GET') {
          return new Response(
            JSON.stringify({
              items: [
                {
                  id: 21,
                  ruleset_key: 'field-day',
                  version: '2026',
                  source_url: null,
                  source_edition: null,
                  rule_type_keys: requiredRules,
                  created_at: '2026-01-01T00:00:00Z',
                },
              ],
            }),
            { status: 200 },
          )
        }
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
    expect(
      (wrapper.findAll('.metadata-panel input')[1]?.element as HTMLInputElement)
        .value,
    ).toBe('2026')
    expect(wrapper.text()).toContain(
      'Enter a new version identifier; saved versions cannot be changed',
    )
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

  it('continues to load a saved version from its contest edit link', async () => {
    const configuration = {
      schema_version: 2,
      ruleset_key: 'field-day',
      version: '2026',
      rules: requiredRules.map((kind) => ({ id: kind, rule: { kind } })),
    }
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
        if (path.endsWith('/rulesets/versions/21'))
          return new Response(JSON.stringify({ id: 21, configuration }), {
            status: 200,
          })
        throw new Error(`Unexpected request ${path}`)
      }),
    )

    const wrapper = mount(RulesetComposerView, {
      props: { editVersionId: '21' },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Editing field-day version 2026')
    expect(
      (wrapper.get('.metadata-panel input').element as HTMLInputElement).value,
    ).toBe('field-day')
    expect(
      (wrapper.findAll('.metadata-panel input')[1]?.element as HTMLInputElement)
        .value,
    ).toBe('2026')
  })
})
