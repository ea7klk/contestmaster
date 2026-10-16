import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EligibilityCatalogEditor from './EligibilityCatalogEditor.vue'

describe('EligibilityCatalogEditor', () => {
  it('shows advisory no-contest status with text and red styling and emits selection', async () => {
    const wrapper = mount(EligibilityCatalogEditor, {
      props: {
        kind: 'band',
        selected: [],
        items: [
          {
            id: 1,
            kind: 'band',
            key: '60m',
            label: '60 m',
            description: 'Shared band label',
            frequency_range: '5 MHz',
            sort_order: 1,
            is_active: true,
            contest_free: true,
          },
        ],
      },
    })
    expect(wrapper.text()).toContain('No-contest band (advisory)')
    expect(wrapper.text()).toContain('does not automatically exclude the band')
    expect(wrapper.get('.contest-free-band').attributes('class')).toContain(
      'contest-free-band',
    )
    await wrapper.get('input[type="checkbox"]').setValue(true)
    expect(wrapper.emitted('update:selected')?.[0]?.[0]).toEqual(['60m'])
  })
})
