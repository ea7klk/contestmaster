import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RulesetComposerView from './RulesetComposerView.vue'

const drafts = import.meta.glob(
  '../../../documentation/ruleset-drafts/*.json',
  {
    eager: true,
    import: 'default',
  },
) as Record<
  string,
  {
    schema_version: number
    ruleset_key: string
    version: string
    rules: Array<{ id: string; rule: Record<string, unknown> }>
  }
>

const requiredKinds = [
  'submission',
  'categories',
  'exchange',
  'eligibility',
  'duplicates',
  'points',
  'score_formula',
  'format_mapping',
]

afterEach(() => vi.unstubAllGlobals())

async function navigateToReview(wrapper: ReturnType<typeof mount>) {
  await wrapper.findAll('.step-navigation button')[4]?.trigger('click')
  await flushPromises()
}

function catalogResponse() {
  return {
    rule_types: requiredKinds.map((key) => ({
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

describe('documented contest starter drafts', () => {
  it.each(Object.entries(drafts))(
    'imports and validates %s through the composer',
    async (_path, draft) => {
      const sentDrafts: Array<Record<string, unknown>> = []
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
          if (String(input).endsWith('/rulesets/catalog')) {
            return new Response(JSON.stringify(catalogResponse()), {
              status: 200,
            })
          }
          if (
            String(input).endsWith('/rulesets/bands') ||
            String(input).endsWith('/rulesets/modes')
          ) {
            return new Response(JSON.stringify({ items: [] }), { status: 200 })
          }
          sentDrafts.push(
            JSON.parse(String(init?.body)) as Record<string, unknown>,
          )
          return new Response(
            JSON.stringify({
              valid: true,
              ruleset_key: draft.ruleset_key,
              version: draft.version,
              rule_types: requiredKinds,
              summary: `${draft.ruleset_key} version ${draft.version}`,
              worked_score_example: { final_score: 1, steps: [] },
            }),
            { status: 200 },
          )
        }),
      )

      const wrapper = mount(RulesetComposerView)
      await flushPromises()
      await navigateToReview(wrapper)
      const input = wrapper.get('input[type="file"]')
      const file = new File([JSON.stringify(draft)], 'starter.json', {
        type: 'application/json',
      })
      Object.defineProperty(file, 'text', {
        value: async () => JSON.stringify(draft),
      })
      Object.defineProperty(input.element, 'files', {
        configurable: true,
        value: [file],
      })
      await input.trigger('change')
      await flushPromises()
      expect(
        (wrapper.get('input[autocomplete="off"]').element as HTMLInputElement)
          .value,
      ).toBe(draft.ruleset_key)

      await wrapper.get('.step-controls .primary-button').trigger('click')
      await flushPromises()

      expect(sentDrafts).toHaveLength(1)
      expect(sentDrafts[0]?.ruleset_key).toBe(draft.ruleset_key)
      expect(sentDrafts[0]?.rules).toMatchObject(draft.rules)
      for (const configured of sentDrafts[0]?.rules as Array<{
        rule: Record<string, unknown>
      }>) {
        if (
          configured.rule.kind !== 'format_mapping' ||
          configured.rule.format !== 'cabrillo'
        )
          continue
        const mappings = configured.rule.category_mappings as Array<
          Record<string, unknown>
        >
        expect(
          mappings.every(
            (mapping) => typeof mapping.external_field === 'string',
          ),
        ).toBe(true)
      }
    },
  )
})
