import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
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
      path: '/manage/contests/new',
      name: 'contest-create',
      component: () => import('./views/ContestEditorView.vue'),
    },
    {
      path: '/manage/contests/:contestId/edit',
      name: 'contest-edit',
      component: () => import('./views/ContestEditorView.vue'),
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
      path: '/reset-password',
      name: 'system-reset-password',
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
      path: '/participant/reset-password',
      name: 'participant-reset-password',
      component: () => import('./views/ParticipantAccessView.vue'),
    },
    {
      path: '/participant/confirm-email-change',
      name: 'participant-confirm-email-change',
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
      path: '/admin/users',
      name: 'user-admin',
      component: () => import('./views/UserAdminView.vue'),
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
      path: '/manage/rulesets',
      name: 'ruleset-manager',
      component: () => import('./views/RulesetManagerView.vue'),
    },
    {
      path: '/manage/rulesets/new',
      name: 'ruleset-create',
      component: () => import('./views/RulesetComposerView.vue'),
    },
    {
      path: '/manage/rulesets/:editVersionId/edit',
      name: 'ruleset-edit',
      component: () => import('./views/RulesetComposerView.vue'),
      props: (route) => ({
        editVersionId: route.params.editVersionId as string,
      }),
    },
    {
      path: '/rulesets/compose/:editVersionId?',
      name: 'ruleset-composer',
      redirect: (route) =>
        route.params.editVersionId
          ? `/manage/rulesets/${String(route.params.editVersionId)}/edit`
          : '/manage/rulesets',
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
