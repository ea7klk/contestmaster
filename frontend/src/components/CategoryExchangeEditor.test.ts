import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { expectAccessible } from '../test/a11y'
import { setLocale } from '../i18n'
import CategoryExchangeEditor from './CategoryExchangeEditor.vue'

describe('CategoryExchangeEditor', () => {
  it('explains category dimensions and starts preset values unchecked', async () => {
    const wrapper = mount(CategoryExchangeEditor, {
      props: {
        kind: 'categories',
        modelValue: { kind: 'categories', dimensions: [] },
      },
    })
    expect(wrapper.text()).toContain('classification axes')
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({
      modelValue: wrapper.emitted('update:modelValue')?.[0]?.[0] as Record<
        string,
        unknown
      >,
    })
    const key = wrapper.get('select')
    await key.setValue('power')
    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as {
      dimensions: Array<{ key: string; label: string; choices: unknown[] }>
    }
    expect(emitted.dimensions[0]).toMatchObject({
      key: 'power',
      label: 'Power',
    })
    expect(emitted.dimensions[0]?.choices).toEqual([])
    await wrapper.setProps({ modelValue: emitted })
    const qrp = wrapper
      .findAll('fieldset.preset-choice-selector label')
      .find((label) => label.text().trim() === 'QRP')
    expect(qrp?.get('input').element.checked).toBe(false)
    await qrp!.get('input').setValue(true)
    const selected = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as {
      dimensions: Array<{ choices: Array<{ key: string; label: string }> }>
    }
    expect(selected.dimensions[0]?.choices).toEqual([
      { key: 'qrp', label: 'QRP', requires_declaration: false },
    ])
    await wrapper.setProps({ modelValue: selected })
    expect(wrapper.text()).toContain('no universal contest wattage thresholds')
  })

  it('lets authors add precise explanations to category dimensions and choices', async () => {
    const wrapper = mount(CategoryExchangeEditor, {
      props: {
        kind: 'categories',
        modelValue: {
          kind: 'categories',
          dimensions: [
            {
              key: 'power',
              label: 'Power',
              required: true,
              choices: [{ key: 'qrp', label: 'QRP' }],
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain(
      'measurement point, or qualification details',
    )
    await wrapper
      .get('textarea[aria-label="Contest-specific dimension explanation"]')
      .setValue('Measured at the antenna connector.')
    const dimensionDraft = wrapper
      .emitted('update:modelValue')
      ?.at(-1)?.[0] as {
      dimensions: Array<Record<string, unknown>>
    }
    expect(dimensionDraft.dimensions[0]?.description).toBe(
      'Measured at the antenna connector.',
    )
    await wrapper.setProps({ modelValue: dimensionDraft })

    await wrapper
      .get('textarea[aria-label="Contest-specific choice explanation"]')
      .setValue('The contest limit is 5 W output.')
    const choiceDraft = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as {
      dimensions: Array<{ choices: Array<Record<string, unknown>> }>
    }
    expect(choiceDraft.dimensions[0]?.choices[0]?.description).toBe(
      'The contest limit is 5 W output.',
    )
    await expectAccessible(wrapper.element)
  })

  it('derives a readable custom dimension label from its stable key', async () => {
    const wrapper = mount(CategoryExchangeEditor, {
      props: {
        kind: 'categories',
        modelValue: {
          kind: 'categories',
          dimensions: [
            {
              key: 'custom-class',
              label: 'Old label',
              required: true,
              choices: [{ key: 'a', label: 'Class A' }],
            },
          ],
        },
      },
    })

    const customKey = wrapper.get('input')
    await customKey.setValue('operator-class')
    const updated = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as {
      dimensions: Array<Record<string, unknown>>
    }
    expect(updated.dimensions[0]).toMatchObject({
      key: 'operator-class',
      label: 'Operator Class',
      required: true,
      choices: [{ key: 'a', label: 'Class A' }],
    })
    await wrapper.setProps({ modelValue: updated })

    expect(wrapper.get('.dimension-label-field output').text()).toBe(
      'Operator Class',
    )
    expect(wrapper.find('.dimension-label-field input').exists()).toBe(false)
  })

  it('selects preset values with display labels and keeps keys in the existing choices payload', async () => {
    const wrapper = mount(CategoryExchangeEditor, {
      props: {
        kind: 'categories',
        modelValue: {
          kind: 'categories',
          dimensions: [
            {
              key: 'power',
              label: 'Station power',
              required: true,
              choices: [
                {
                  key: 'qrp',
                  label: 'QRP',
                  description: 'Sponsor limit: 5 W.',
                  requires_declaration: true,
                },
              ],
            },
          ],
        },
      },
    })

    const selector = wrapper.get('fieldset.preset-choice-selector')
    expect(selector.get('legend').text()).toBe(
      'Accepted values for Station power',
    )
    expect(selector.text()).toContain('Low power')
    expect(selector.text()).not.toContain('(low)')
    const qrp = selector
      .findAll('label')
      .find((label) => label.text().trim() === 'QRP')
    const low = selector
      .findAll('label')
      .find((label) => label.text().trim() === 'Low power')
    expect(qrp?.get('input').element.checked).toBe(true)
    expect(low?.get('input').element.checked).toBe(false)

    await low!.get('input').setValue(true)
    const updated = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as {
      dimensions: Array<{
        choices: Array<Record<string, unknown>>
      }>
    }
    expect(updated.dimensions[0]?.choices).toEqual([
      {
        key: 'qrp',
        label: 'QRP',
        description: 'Sponsor limit: 5 W.',
        requires_declaration: true,
      },
      { key: 'low', label: 'Low power', requires_declaration: false },
    ])
    await expectAccessible(wrapper.element)
  })

  it('offers common exchange keys and explains key/label stability', async () => {
    const wrapper = mount(CategoryExchangeEditor, {
      props: { kind: 'exchange', modelValue: { kind: 'exchange', fields: [] } },
    })
    expect(wrapper.text()).toContain('stable references')
    await wrapper.get('button').trigger('click')
    await wrapper.setProps({
      modelValue: wrapper.emitted('update:modelValue')?.[0]?.[0] as Record<
        string,
        unknown
      >,
    })
    await wrapper.get('select').setValue('serial')
    const emitted = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as {
      fields: Array<Record<string, unknown>>
    }
    expect(emitted.fields[0]).toMatchObject({
      key: 'serial',
      label: 'Serial number',
      value_type: 'serial',
      direction: 'both',
    })
  })

  it('localizes preset labels without changing the configured key or label', async () => {
    await setLocale('de', undefined)
    const wrapper = mount(CategoryExchangeEditor, {
      props: {
        kind: 'categories',
        modelValue: {
          kind: 'categories',
          dimensions: [
            {
              key: 'power',
              label: 'Power',
              required: true,
              choices: [],
            },
          ],
        },
      },
    })

    expect(wrapper.get('.controlled-row select').text()).toContain('Leistung')
    await wrapper.get('.controlled-row select').setValue('operator')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      dimensions: [
        expect.objectContaining({ key: 'operator', label: 'Operator' }),
      ],
    })
    wrapper.unmount()
    await setLocale('en', undefined)
  })

  it('groups category and choice controls into wrapping editor rows', async () => {
    const wrapper = mount(CategoryExchangeEditor, {
      props: {
        kind: 'categories',
        modelValue: {
          kind: 'categories',
          dimensions: [
            {
              key: 'assisted',
              label: 'Assistance',
              required: true,
              choices: [
                {
                  key: 'assisted',
                  label: 'Assisted',
                  requires_declaration: false,
                },
              ],
            },
          ],
        },
      },
    })

    expect(wrapper.find('.controlled-row').exists()).toBe(true)
    expect(wrapper.find('.controlled-choice-list').exists()).toBe(true)
    expect(wrapper.find('.controlled-choice').findAll('label')).toHaveLength(4)
    expect(
      wrapper
        .find('.controlled-row')
        .findAll('button')
        .some((button) => button.text() === 'Add choice'),
    ).toBe(true)
    await expectAccessible(wrapper.element)
  })
})
