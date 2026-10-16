import { config } from '@vue/test-utils'
import { beforeEach } from 'vitest'
import { i18n, translateText } from '../i18n'

config.global.plugins = [
  ...(config.global.plugins ?? []),
  {
    install(app) {
      app.use(i18n)
      app.config.globalProperties.$tr = translateText
    },
  },
]

beforeEach(() => {
  i18n.global.locale.value = 'en'
  document.documentElement.lang = 'en'
})
