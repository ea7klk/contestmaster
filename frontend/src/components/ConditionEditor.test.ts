import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConditionEditor from './ConditionEditor.vue'

describe('ConditionEditor', () => {
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
})
