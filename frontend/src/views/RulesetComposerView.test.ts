import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
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

afterEach(() => vi.unstubAllGlobals())

describe('RulesetComposerView', () => {
  it('loads required rule types and sends the configured draft for validation', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).endsWith('/rulesets/catalog')) {
          return new Response(JSON.stringify(catalogResponse()), {
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

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[role="status"]').text()).toContain('Ruleset is valid')
    expect(wrapper.text()).toContain('Worked integer score example')
  })

  it('shows API validation errors without replacing the draft with a success result', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/rulesets/catalog')) {
        return new Response(JSON.stringify(catalogResponse()), { status: 200 })
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

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(wrapper.get('[role="status"]').text()).toContain(
      'Saved my-contest version 1',
    )
  })
})
