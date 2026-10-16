import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { JsonSchema } from '../api/rulesets'
import RuleSchemaEditor from './RuleSchemaEditor.vue'

describe('RuleSchemaEditor', () => {
  it('renders one checkbox for each boolean setting, without a Configure toggle', async () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        reject_self_contacts: {
          type: 'boolean',
          default: true,
          title: 'Reject self contacts',
        },
        manager_extension_allowed: {
          type: 'boolean',
          default: false,
          title: 'Manager extension allowed',
        },
      },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: {
          reject_self_contacts: true,
          manager_extension_allowed: false,
        },
        label: 'Eligibility settings',
      },
    })

    const booleanLabels = wrapper.findAll('label.schema-boolean')
    expect(booleanLabels).toHaveLength(2)
    expect(wrapper.text()).not.toContain('Configure')
    expect(booleanLabels[0].text()).toContain('Reject self contacts')
    expect(booleanLabels[0].get('input').element.checked).toBe(true)
    expect(booleanLabels[1].text()).toContain('Manager extension allowed')
    expect(booleanLabels[1].get('input').element.checked).toBe(false)

    await booleanLabels[0].get('input').setValue(false)
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      reject_self_contacts: false,
      manager_extension_allowed: false,
    })
  })

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

  it('keeps generated fields within consistent nested field groups', () => {
    const schema: JsonSchema = {
      type: 'object',
      title: 'Eligibility settings',
      properties: {
        reject_self_contacts: {
          type: 'boolean',
          title: 'Reject self contacts',
          description: 'Do not credit contacts made with the entrant own call.',
        },
        action: {
          type: 'string',
          title: 'Failure action',
          enum: ['not_credited', 'needs_review'],
          description: 'Choose how to handle a contact that fails a check.',
        },
      },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: {
          reject_self_contacts: true,
          action: 'not_credited',
        },
      },
    })

    expect(wrapper.findAll('.schema-field')).toHaveLength(2)
    expect(wrapper.findAll('.schema-editor-nested')).toHaveLength(1)
    expect(wrapper.text()).toContain('Do not credit contacts')
    expect(wrapper.text()).toContain('Choose how to handle a contact')
  })
})
