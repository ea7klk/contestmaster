import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n, initializeLocale, translateText } from './i18n'
import './style.css'

async function startApplication() {
  await initializeLocale()
  const app = createApp(App)
  app.config.globalProperties.$tr = translateText
  app.use(createPinia()).use(i18n).use(router).mount('#app')
}

void startApplication()
