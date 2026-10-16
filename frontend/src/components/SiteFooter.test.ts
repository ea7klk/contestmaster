import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { router } from '../router'
import App from '../App.vue'
import SiteFooter from './SiteFooter.vue'

describe('SiteFooter', () => {
  it('provides a keyboard-accessible attribution link to source license terms', () => {
    const wrapper = mount(SiteFooter)
    const footer = wrapper.get('footer')
    expect(footer.classes()).toContain('site-footer')
    expect(footer.text()).toContain(
      'Copyright © 2026 Volker Kerkhoff and contributors. Contestmaster is licensed under AGPL-3.0-only.',
    )
    const repository = wrapper.get(
      'a[href="https://github.com/ea7klk/contestmaster"]',
    )
    expect(repository.text()).toBe('Project repository')
    const projectLicense = wrapper.get(
      'a[href="https://github.com/ea7klk/contestmaster/blob/main/LICENSE"]',
    )
    expect(projectLicense.text()).toBe('License')

    const license = wrapper.get(
      'a[href="https://github.com/WSJTX/wsjtx/blob/master/cty.dat_copyright.txt"]',
    )
    expect(license.text()).toBe('license and use terms')
    expect(license.attributes('target')).toBe('_blank')
    expect(license.attributes('rel')).toContain('noreferrer')

    expect(wrapper.text()).not.toMatch(/UNGEGN|M49|United Nations/i)
    for (const link of [repository, projectLicense, license]) {
      expect(link.attributes('target')).toBe('_blank')
      expect(link.attributes('rel')).toContain('noreferrer')
    }
  })

  it('is part of the shared shell on the routed application page', async () => {
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })

    expect(wrapper.get('footer').text()).toContain('license and use terms')
    expect(wrapper.get('footer').text()).toContain('Copyright © 2026 Volker Kerkhoff and contributors.')
    expect(wrapper.find('footer a[href="https://github.com/ea7klk/contestmaster"]').exists()).toBe(true)
    expect(wrapper.get('footer').text()).not.toMatch(/UNGEGN|M49|United Nations/i)
  })

  it('keeps licensed source links in the shared shell across every frontend route', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({ error: { message: 'Authentication is required.' } }),
          { status: 401 },
        ),
      ),
    )
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [createPinia(), router] } })
    const paths = [
      '/',
      '/contests/public-sprint/results',
      '/manage/contests/4/results',
      '/submit-log',
      '/entries/4/manage',
      '/sign-in',
      '/participant/access',
      '/participant/verify?token=example',
      '/participant/entries',
      '/admin/master-data',
      '/manage/contests',
      '/rulesets/compose',
    ]
    for (const path of paths) {
      await router.push(path)
      await flushPromises()
      expect(wrapper.get('footer').text(), path).toContain('cty.dat')
      expect(wrapper.find('footer a[href="https://www.country-files.com/cty/"]').exists(), path).toBe(true)
      expect(wrapper.get('footer').text(), path).not.toMatch(/UNGEGN|M49|United Nations/i)
    }
  })
})
