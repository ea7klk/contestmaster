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
      path: '/contests/:slug',
      name: 'public-contest',
      component: () => import('./views/PublicContestView.vue'),
      props: true,
    },
    {
      path: '/contests/:slug/results',
      name: 'contest-results',
      component: () => import('./views/ContestResultsView.vue'),
      props: true,
    },
    {
      path: '/manage/contests/:contestId/results',
      name: 'contest-results-manager',
      component: () => import('./views/ContestResultsManagerView.vue'),
      props: true,
    },
    {
      path: '/manage/contests/:contestId/entries/:entryId?',
      name: 'contest-entries',
      component: () => import('./views/ContestEntriesView.vue'),
    },
    {
      path: '/submit-log',
      name: 'log-submission',
      component: () => import('./views/LogSubmissionView.vue'),
    },
    {
      path: '/entries/:entryId/manage',
      name: 'entry-management',
      component: () => import('./views/EntryManagementView.vue'),
      props: true,
    },
    {
      path: '/sign-in',
      name: 'sign-in',
      component: () => import('./views/SignInView.vue'),
    },
    {
      path: '/participant/access',
      name: 'participant-access',
      component: () => import('./views/ParticipantAccessView.vue'),
    },
    {
      path: '/participant/verify',
      name: 'participant-verify',
      component: () => import('./views/ParticipantAccessView.vue'),
    },
    {
      path: '/participant/entries',
      name: 'participant-entries',
      component: () => import('./views/ParticipantAccessView.vue'),
    },
    {
      path: '/admin/master-data',
      name: 'master-data-admin',
      component: () => import('./views/MasterDataAdminView.vue'),
    },
    {
      path: '/admin/operating-catalog',
      name: 'operating-catalog-admin',
      component: () => import('./views/OperatingCatalogAdminView.vue'),
    },
    {
      path: '/manage/contests',
      name: 'contest-manager',
      component: () => import('./views/ContestManagerView.vue'),
    },
    {
      path: '/rulesets/compose/:editVersionId?',
      name: 'ruleset-composer',
      component: () => import('./views/RulesetComposerView.vue'),
      props: (route) => ({
        editVersionId: route.params.editVersionId as string | undefined,
      }),
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
