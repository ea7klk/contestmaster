import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { JsonSchema } from '../api/rulesets'
import RuleSchemaEditor from './RuleSchemaEditor.vue'

describe('RuleSchemaEditor', () => {
  it('edits patternProperties maps and keeps parameter values typed', async () => {
    const schema: JsonSchema = {
      type: 'object',
      title: 'Parameters',
      patternProperties: {
        '^[a-z][a-z0-9_.-]*$': {
          anyOf: [
            { type: 'string' },
            { type: 'integer' },
            { type: 'boolean' },
            { type: 'array', items: { type: 'string' } },
            { type: 'null' },
          ],
        },
      },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: {},
        path: 'workflow-parameters',
      },
    })

    await wrapper.get('button.secondary-button').trigger('click')
    await flushPromises()
    await wrapper.setProps({
      modelValue: wrapper.emitted('update:modelValue')?.[0]?.[0],
    })
    expect(wrapper.text()).toContain('Value type')
    await wrapper.get('select').setValue('integer')
    await flushPromises()
    await wrapper.setProps({
      modelValue: wrapper.emitted('update:modelValue')?.at(-1)?.[0],
    })
    await wrapper.get('input[type="number"]').setValue('42')

    const updates = wrapper.emitted('update:modelValue') ?? []
    expect(updates.at(-1)?.[0]).toEqual({ value: 42 })
  })
})
