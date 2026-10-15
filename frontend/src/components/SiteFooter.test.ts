import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createPinia } from 'pinia'
import { router } from '../router'
import App from '../App.vue'
import SiteFooter from './SiteFooter.vue'

describe('SiteFooter', () => {
  it('provides a keyboard-accessible attribution link to source license terms', () => {
    const wrapper = mount(SiteFooter)
    const license = wrapper.get(
      'a[href="https://github.com/WSJTX/wsjtx/blob/master/cty.dat_copyright.txt"]',
    )
    expect(license.text()).toBe('license and use terms')
    expect(license.attributes('target')).toBe('_blank')
    expect(license.attributes('rel')).toContain('noreferrer')

    const ungegnTerms = wrapper.get(
      'a[href="https://unstats.un.org/unsd/ungegn/meetings/Bureau_Divisions/documents/UNGEGN_Bureau_WGN_November_2023_updated.pdf"]',
    )
    expect(ungegnTerms.text()).toBe('open access terms')
    for (const link of [license, ungegnTerms]) {
      expect(link.attributes('target')).toBe('_blank')
      expect(link.attributes('rel')).toContain('noreferrer')
    }
  })

  it('is part of the shared shell on the routed application page', async () => {
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })

    expect(wrapper.get('footer').text()).toContain('license and use terms')
    expect(wrapper.get('footer').text()).toContain('open access terms')
  })
})
