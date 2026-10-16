import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { expectAccessible } from '../test/a11y'
import ConditionEditor from './ConditionEditor.vue'

describe('ConditionEditor', () => {
  it('explains fact paths and gives readable comparison choices', async () => {
    const wrapper = mount(ConditionEditor)

    await expectAccessible(wrapper.element)
    expect(wrapper.text()).toContain(
      'A condition compares supported contest data',
    )
    expect(wrapper.text()).toContain('Examples: qso.band, qso.entity.')
    expect(wrapper.findAll('select')[1]!.text()).toContain('Equals (eq)')
    expect(wrapper.findAll('select')[1]!.text()).toContain(
      'Is present (exists)',
    )
  })

  it('switches membership comparisons to a list value', async () => {
    const wrapper = mount(ConditionEditor, {
      props: {
        modelValue: {
          kind: 'compare',
          fact: 'qso.band',
          operator: 'eq',
          value: '20m',
        },
      },
    })

    await wrapper.findAll('select')[1].setValue('in')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      kind: 'compare',
      fact: 'qso.band',
      operator: 'in',
      value: ['20m'],
    })
  })

  it('explains combined and negated conditions', async () => {
    const wrapper = mount(ConditionEditor, {
      props: {
        modelValue: {
          kind: 'all',
          conditions: [
            { kind: 'compare', fact: 'qso.band', operator: 'eq', value: '20m' },
          ],
        },
      },
    })
    expect(wrapper.text()).toContain('Every condition below must match')

    await wrapper.setProps({
      modelValue: {
        kind: 'not',
        condition: {
          kind: 'compare',
          fact: 'qso.band',
          operator: 'eq',
          value: '20m',
        },
      },
    })
    expect(wrapper.text()).toContain(
      'true only when its nested condition is false',
    )
  })
})
