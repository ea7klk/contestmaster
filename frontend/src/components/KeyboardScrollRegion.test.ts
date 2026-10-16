import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KeyboardScrollRegion from './KeyboardScrollRegion.vue'

describe('KeyboardScrollRegion', () => {
  it('scrolls horizontally with arrow keys and jumps to either end', async () => {
    const wrapper = mount(KeyboardScrollRegion, {
      props: { label: 'Published standings', scrollStep: 120 },
      slots: {
        default: '<table><tbody><tr><td>Standings</td></tr></tbody></table>',
      },
    })
    const element = wrapper.element
    Object.defineProperties(element, {
      scrollWidth: { configurable: true, value: 900 },
      clientWidth: { configurable: true, value: 300 },
    })

    expect(wrapper.attributes('role')).toBe('region')
    expect(wrapper.attributes('aria-label')).toContain(
      'Use the left and right arrow keys',
    )
    expect(wrapper.attributes('aria-keyshortcuts')).toBe(
      'ArrowLeft ArrowRight Home End',
    )

    await wrapper.trigger('keydown', { key: 'ArrowRight' })
    expect(element.scrollLeft).toBe(120)
    await wrapper.trigger('keydown', { key: 'End' })
    expect(element.scrollLeft).toBe(600)
    await wrapper.trigger('keydown', { key: 'ArrowLeft' })
    expect(element.scrollLeft).toBe(480)
    await wrapper.trigger('keydown', { key: 'Home' })
    expect(element.scrollLeft).toBe(0)
  })

  it('does not intercept keys when horizontal overflow is absent', async () => {
    const wrapper = mount(KeyboardScrollRegion, {
      props: { label: 'Short content' },
    })
    Object.defineProperties(wrapper.element, {
      scrollWidth: { configurable: true, value: 300 },
      clientWidth: { configurable: true, value: 300 },
    })
    const event = new KeyboardEvent('keydown', {
      key: 'ArrowRight',
      cancelable: true,
    })
    wrapper.element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
  })
})
