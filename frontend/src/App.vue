<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from './api/client'
import { getCurrentUser, signOut, type PrivilegedUser } from './api/identity'
import SiteFooter from './components/SiteFooter.vue'

const route = useRoute()
const router = useRouter()
const staffUser = ref<PrivilegedUser | null>(null)
const signOutError = ref('')

async function refreshIdentity() {
  try {
    staffUser.value = await getCurrentUser()
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 401) {
      staffUser.value = null
      return
    }
    signOutError.value = 'Staff session status could not be refreshed.'
  }
}

async function handleSignOut() {
  signOutError.value = ''
  try {
    await signOut()
    staffUser.value = null
    await router.push('/')
  } catch (error) {
    signOutError.value =
      error instanceof ApiError
        ? error.message
        : 'Sign-out could not be completed.'
  }
}

onMounted(refreshIdentity)
watch(() => route.fullPath, refreshIdentity)
</script>

<template>
  <div class="app-shell">
    <header class="site-header">
      <a class="wordmark" href="/" aria-label="Contestmaster home"
        >Contestmaster</a
      >
      <span class="header-caption">Amateur radio contest engine</span>
      <nav aria-label="Main navigation" class="site-navigation">
        <RouterLink to="/manage/contests">Manage contests</RouterLink>
        <RouterLink to="/rulesets/compose">Ruleset composer</RouterLink>
        <RouterLink to="/participant/access">Participant access</RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/master-data"
        >
          Master data
        </RouterLink>
        <RouterLink v-if="!staffUser" to="/sign-in">Staff sign-in</RouterLink>
        <button
          v-else
          class="sign-out-button"
          type="button"
          @click="handleSignOut"
        >
          Sign out {{ staffUser.display_name }}
        </button>
      </nav>
    </header>
    <p v-if="signOutError" class="shell-error" role="alert">
      {{ signOutError }}
    </p>
    <main id="main-content" class="main-content">
      <RouterView />
    </main>
    <SiteFooter />
  </div>
</template>
