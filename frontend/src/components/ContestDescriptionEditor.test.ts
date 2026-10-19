import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContestDescriptionEditor from './ContestDescriptionEditor.vue'

describe('ContestDescriptionEditor', () => {
  it('loads stored Markdown, offers rich text controls, and previews sanitized output', async () => {
    const wrapper = mount(ContestDescriptionEditor, {
      props: {
        modelValue:
          '## Event details\n\nA **bold** note and [rules](https://example.org/rules).',
      },
    })
    await flushPromises()

    const editor = wrapper.get('[contenteditable="true"]')
    expect(editor.get('h2').text()).toBe('Event details')
    expect(editor.get('strong').text()).toBe('bold')
    expect(editor.get('a').attributes('href')).toBe('https://example.org/rules')
    expect(wrapper.get('.preview-content h2').text()).toBe('Event details')
    expect(wrapper.get('.preview-content strong').text()).toBe('bold')
    expect(wrapper.findAll('.rich-text-toolbar button')).toHaveLength(9)
  })

  it('updates both the editor and preview when the stored Markdown changes', async () => {
    const wrapper = mount(ContestDescriptionEditor, {
      props: { modelValue: 'Original text' },
    })
    await flushPromises()
    await wrapper.setProps({ modelValue: 'Updated **description**' })
    await flushPromises()

    expect(wrapper.get('[contenteditable="true"]').text()).toContain(
      'Updated description',
    )
    expect(wrapper.get('.preview-content strong').text()).toBe('description')
  })

  it('emits edited rich text as Markdown', async () => {
    const wrapper = mount(ContestDescriptionEditor, {
      props: { modelValue: 'Original text' },
    })
    await flushPromises()

    const surface = wrapper.get('[contenteditable="true"]')
    surface.element.textContent = 'Changed text'
    await surface.trigger('input')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe(
      'Changed text',
    )
  })

  it('does not render unsafe HTML in its preview', async () => {
    const wrapper = mount(ContestDescriptionEditor, {
      props: {
        modelValue:
          'Safe **text** <script>alert(1)</script> <img src=x onerror=alert(1)>',
      },
    })
    await flushPromises()

    const preview = wrapper.get('.preview-content')
    expect(preview.find('strong').text()).toBe('text')
    expect(preview.find('script').exists()).toBe(false)
    expect(preview.find('img').exists()).toBe(false)
  })

  it('keeps Markdown tables visible in the rich text editor and preview', async () => {
    const wrapper = mount(ContestDescriptionEditor, {
      props: {
        modelValue: '| Band | QSOs |\n| --- | ---: |\n| 20 m | 12 |',
      },
    })
    await flushPromises()

    expect(wrapper.get('[contenteditable="true"] table').text()).toContain(
      '20 m',
    )
    expect(wrapper.get('[contenteditable="true"] table').text()).toContain('12')
    expect(wrapper.get('.preview-content table').text()).toContain('20 m')
    expect(wrapper.get('.preview-content table').text()).toContain('12')
  })
})
