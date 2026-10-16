<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from './api/client'
import { getCurrentUser, signOut, type PrivilegedUser } from './api/identity'
import SiteFooter from './components/SiteFooter.vue'

const route = useRoute()
const router = useRouter()
const staffUser = ref<PrivilegedUser | null>(null)
const signOutError = ref('')
const menuOpen = ref(false)
const menuButton = ref<HTMLButtonElement | null>(null)

function closeMenu(restoreFocus = false) {
  menuOpen.value = false
  if (restoreFocus) {
    void nextTick(() => menuButton.value?.focus())
  }
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && menuOpen.value) {
    event.preventDefault()
    closeMenu(true)
  }
}

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

onMounted(() => {
  refreshIdentity()
  document.addEventListener('keydown', handleGlobalKeydown)
})
onBeforeUnmount(() =>
  document.removeEventListener('keydown', handleGlobalKeydown),
)
watch(
  () => route.fullPath,
  () => {
    closeMenu()
    refreshIdentity()
  },
)
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">Skip to content</a>
    <header class="site-header">
      <div class="site-header-row">
        <a class="wordmark" href="/" aria-label="Contestmaster home"
          >Contestmaster</a
        >
        <span class="header-caption">Amateur radio contest engine</span>
        <RouterLink class="header-upload-action" to="/submit-log">
          Submit a log
        </RouterLink>
        <button
          ref="menuButton"
          class="menu-toggle"
          type="button"
          :aria-expanded="menuOpen"
          aria-controls="main-navigation"
          :aria-label="menuOpen ? 'Close main menu' : 'Open main menu'"
          @click="menuOpen = !menuOpen"
        >
          <span aria-hidden="true" class="menu-toggle-lines"></span>
        </button>
      </div>
      <nav
        id="main-navigation"
        aria-label="Main navigation"
        class="site-navigation"
        :class="{ 'is-open': menuOpen }"
        @click="closeMenu()"
      >
        <RouterLink to="/">Published results</RouterLink>
        <RouterLink to="/manage/contests">Manage contests</RouterLink>
        <RouterLink to="/rulesets/compose">Ruleset composer</RouterLink>
        <RouterLink to="/participant/access">Participant access</RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/master-data"
        >
          Master data
        </RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/operating-catalog"
        >
          Bands and modes
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
