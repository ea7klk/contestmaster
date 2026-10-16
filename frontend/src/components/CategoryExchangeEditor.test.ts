import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { expectAccessible } from '../test/a11y'
import { setLocale } from '../i18n'
import CategoryExchangeEditor from './CategoryExchangeEditor.vue'

describe('CategoryExchangeEditor', () => {
  it('explains category dimensions and applies a preset without changing its stable key on label edits', async () => {
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
    expect(emitted.dimensions[0]?.choices.length).toBe(3)
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

    expect(wrapper.get('.controlled-row select').text()).toContain(
      'Leistung (power)',
    )
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
    expect(wrapper.find('.controlled-choice').findAll('label')).toHaveLength(3)
    expect(
      wrapper
        .find('.controlled-row')
        .findAll('button')
        .some((button) => button.text() === 'Add choice'),
    ).toBe(true)
    await expectAccessible(wrapper.element)
  })
})
