import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { JsonSchema } from '../api/rulesets'
import RuleSchemaEditor from './RuleSchemaEditor.vue'

describe('RuleSchemaEditor', () => {
  it('shows multiplier source facts in a dropdown and emits the chosen fact', async () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        source_fact: { type: 'string', title: 'Source Fact' },
      },
      required: ['source_fact'],
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: { source_fact: '' },
        path: 'rules-3',
        factOptions: [
          { value: 'qso.entity', label: 'Worked station entity (CTY)' },
          { value: 'exchange.received.section', label: 'Section — received' },
        ],
      },
    })

    const sourceFactSelect = wrapper.get('select')
    expect(
      sourceFactSelect.findAll('option').map((option) => option.text()),
    ).toEqual([
      'Choose a fact',
      'Worked station entity (CTY)',
      'Section — received',
    ])
    await sourceFactSelect.setValue('exchange.received.section')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      source_fact: 'exchange.received.section',
    })
  })

  it('keeps an existing source fact visible when it is no longer defined', async () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        source_fact: { type: 'string', title: 'Source Fact' },
      },
      required: ['source_fact'],
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: { source_fact: 'exchange.old_field' },
        path: 'rules-3',
        factOptions: [
          { value: 'qso.entity', label: 'Worked station entity (CTY)' },
        ],
      },
    })

    const options = wrapper.get('select').findAll('option')
    expect(options.map((option) => option.attributes('value'))).toEqual([
      'exchange.old_field',
      'qso.entity',
    ])
    expect(options[0]?.text()).toBe(
      'exchange.old_field (Unavailable in this ruleset)',
    )
  })

  it('offers WWROF QSO fields without allowing a duplicate selection', async () => {
    const columns = [
      'frequency',
      'mode',
      'date',
      'time',
      'callsign_sent',
      'rst_sent',
      'exchange_sent',
      'callsign_received',
      'rst_received',
      'exchange_received',
      'transmitter',
    ]
    const schema: JsonSchema = {
      type: 'array',
      title: 'QSO columns',
      items: { type: 'string', enum: columns },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: columns.slice(0, 10),
        path: 'rules-0-qso_columns',
      },
    })

    const selects = wrapper.findAll('.schema-array-item select')
    expect(selects).toHaveLength(10)
    expect(
      selects.map((select) => (select.element as HTMLSelectElement).value),
    ).toEqual(columns.slice(0, 10))
    const frequencyOption = selects[1]!.find('option[value="frequency"]')
    expect((frequencyOption.element as HTMLOptionElement).disabled).toBe(true)
    await wrapper.get('button.secondary-button').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual([
      ...columns.slice(0, 10),
      'transmitter',
    ])
  })

  it('renders category mapping dimensions and choices as constrained dropdowns', async () => {
    const schema: JsonSchema = {
      type: 'object',
      description:
        "External values map to choices declared by this contest's dimensions.",
      patternProperties: { '^[a-z][a-z0-9_.-]*$': { type: 'string' } },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: {},
        path: 'rules-0-category_mappings-0-category_values',
        categoryDimensions: [
          {
            key: 'power',
            label: 'Power',
            choices: [{ key: 'low', label: 'Low power' }],
          },
        ],
      },
    })

    expect(wrapper.text()).toContain(
      "External values map to choices declared by this contest's dimensions.",
    )
    await wrapper.get('button.secondary-button').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toEqual({
      power: 'low',
    })
    await wrapper.setProps({ modelValue: { power: 'low' } })
    const keySelect = wrapper.get('.schema-map-key select')
    expect(
      keySelect.findAll('option').map((option) => option.text()),
    ).toContain('Power (power)')
    const valueSelect = wrapper.get('.schema-map-value select')
    expect(
      valueSelect.findAll('option').map((option) => option.text()),
    ).toContain('Low power (low)')
  })

  it('limits category value choices to the selected WWROF category header', () => {
    const schema: JsonSchema = {
      type: 'string',
      enum: ['CW', 'HIGH', 'LOW', 'QRP', 'SSB'],
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: 'LOW',
        path: 'rules-0-category_mappings-0-external_value',
        categoryHeader: 'CATEGORY-POWER',
      },
    })

    expect(
      wrapper
        .get('select')
        .findAll('option')
        .map((option) => option.text()),
    ).toEqual(['HIGH', 'LOW', 'QRP'])
  })

  it('restricts standard header aliases to their matching WWROF tags', async () => {
    const schema: JsonSchema = {
      type: 'object',
      propertyNames: { enum: ['callsign', 'contest'] },
      additionalProperties: { type: 'string', enum: ['CALLSIGN', 'CONTEST'] },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: {},
        path: 'rules-0-header_fields',
      },
    })

    await wrapper.get('button.secondary-button').trigger('click')
    await wrapper.setProps({ modelValue: { callsign: 'CALLSIGN' } })
    expect(wrapper.get('.schema-map-key select').element).toBeDefined()
    expect(
      wrapper
        .get('.schema-map-value select')
        .findAll('option')
        .map((option) => option.text()),
    ).toEqual(['CALLSIGN'])
  })

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

  it('keeps each parameter key control grouped with its value editor', async () => {
    const schema: JsonSchema = {
      type: 'object',
      patternProperties: {
        '^[a-z][a-z0-9_.-]*$': {
          anyOf: [
            { type: 'string' },
            { type: 'integer' },
            { type: 'boolean' },
            { type: 'null' },
          ],
        },
      },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: { mode: 'automatic' },
        path: 'workflow-parameters',
      },
    })

    const row = wrapper.get('.schema-map-row')
    expect(row.find('.schema-map-value > .schema-editor-nested').exists()).toBe(
      true,
    )
    expect(row.find('.schema-map-key label').text()).toBe('Key')
    expect(
      (row.find('.schema-map-key input').element as HTMLInputElement).value,
    ).toBe('mode')
    expect(row.find('.schema-map-value .schema-control').text()).toContain(
      'Value type',
    )
    expect(row.find('.schema-map-value select').exists()).toBe(true)
    expect(row.findAll('input')).toHaveLength(2)
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

  it('shows each nested scalar and enum field label only once', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        late_policy: {
          type: 'string',
          title: 'Late policy',
          enum: ['reject', 'accept_late'],
        },
        duplicate_scopes: {
          type: 'array',
          title: 'Scope',
          items: { type: 'string', enum: ['contest', 'band'], title: 'Scope' },
        },
        duplicate_rule: {
          type: 'object',
          title: 'Duplicate rule settings',
          properties: {
            effect: {
              type: 'string',
              title: 'Effect',
              enum: ['ignore', 'penalty'],
            },
            penalty_points: { type: 'integer', title: 'Penalty points' },
          },
        },
        points_rule: {
          type: 'object',
          title: 'Points rule settings',
          properties: {
            fact: { type: 'string', title: 'Fact', enum: ['fixed', 'lookup'] },
            fixed_points: { type: 'integer', title: 'Fixed points' },
            exchange_field: {
              type: 'string',
              title: 'Exchange field',
              enum: ['class', 'section'],
            },
            default_points: { type: 'integer', title: 'Default points' },
          },
        },
        score_formula: {
          type: 'object',
          title: 'Score formula settings',
          properties: {
            variable: { type: 'string', title: 'Variable' },
            constant: { type: 'integer', title: 'Constant' },
          },
        },
      },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: {
          late_policy: 'reject',
          duplicate_scopes: ['contest', 'band'],
          duplicate_rule: { effect: 'ignore', penalty_points: 0 },
          points_rule: {
            fact: 'fixed',
            fixed_points: 1,
            exchange_field: 'class',
            default_points: 0,
          },
          score_formula: { variable: 'contacts', constant: 1 },
        },
      },
    })

    for (const fieldName of [
      'Late policy',
      'Scope 1',
      'Scope 2',
      'Effect',
      'Penalty points',
      'Fact',
      'Fixed points',
      'Exchange field',
      'Default points',
      'Variable',
      'Constant',
    ]) {
      const controlLabels = wrapper
        .findAll('.schema-control, .schema-boolean')
        .filter((label) => label.text().trim().startsWith(fieldName))
      expect(controlLabels, fieldName).toHaveLength(1)
      expect(
        wrapper
          .findAll('.schema-editor-nested > legend')
          .some((legend) => legend.text().trim() === fieldName),
      ).toBe(false)
    }
  })

  it('keeps a label for fixed-value fields without duplicating it', () => {
    const schema: JsonSchema = {
      type: 'object',
      properties: {
        kind: { type: 'string', title: 'Rule type', const: 'fixed' },
      },
    }
    const wrapper = mount(RuleSchemaEditor, {
      props: {
        schema,
        rootSchema: schema,
        modelValue: { kind: 'fixed' },
      },
    })

    expect(
      wrapper
        .findAll('.schema-editor-nested > legend')
        .filter((legend) => legend.text().trim() === 'Rule type'),
    ).toHaveLength(1)
    expect(wrapper.findAll('.schema-control')).toHaveLength(0)
    expect(wrapper.text()).toContain('fixed')
  })
})
