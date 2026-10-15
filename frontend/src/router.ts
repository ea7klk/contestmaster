import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('./views/HomeView.vue'),
    },
    {
      path: '/rulesets/compose',
      name: 'ruleset-composer',
      component: () => import('./views/RulesetComposerView.vue'),
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
