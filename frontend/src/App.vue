<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from './api/client'
import { getCurrentUser, signOut, type PrivilegedUser } from './api/identity'
import { signOutParticipant } from './api/participantIdentity'
import SiteFooter from './components/SiteFooter.vue'
import { i18n, setLocale, supportedLocales, type SupportedLocale } from './i18n'
import {
  participantSession,
  refreshParticipantSession,
  setParticipantSession,
} from './state/participantSession'

const route = useRoute()
const router = useRouter()
const staffUser = ref<PrivilegedUser | null>(null)
const signOutError = ref('')
const localeError = ref('')
const participantSignOutError = ref('')
const participantSigningOut = ref(false)
const menuOpen = ref(false)
const menuButton = ref<HTMLButtonElement | null>(null)
const selectedLocale = computed(
  () => i18n.global.locale.value as SupportedLocale,
)
const participantCallsign = computed(
  () =>
    participantSession.value?.callsigns?.find((item) => item.is_primary)
      ?.callsign ??
    participantSession.value?.callsign ??
    '',
)

async function changeLocale(event: Event) {
  const locale = (event.target as HTMLSelectElement).value
  if (supportedLocales.includes(locale as SupportedLocale)) {
    try {
      await setLocale(locale as SupportedLocale)
    } catch {
      localeError.value = 'The selected language could not be loaded.'
    }
  }
}

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
    if (
      staffUser.value.must_change_password &&
      route.path !== '/change-password'
    ) {
      await router.replace({
        path: '/change-password',
        query: { next: route.fullPath },
      })
    }
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

async function handleParticipantSignOut() {
  participantSignOutError.value = ''
  participantSigningOut.value = true
  try {
    await signOutParticipant()
    setParticipantSession(null)
    await router.replace('/')
  } catch (error) {
    participantSignOutError.value =
      error instanceof ApiError
        ? error.message
        : 'Participant sign-out could not be completed.'
  } finally {
    participantSigningOut.value = false
  }
}

onMounted(() => {
  refreshIdentity()
  refreshParticipantSession()
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
    refreshParticipantSession()
  },
)
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">{{ $tr('Skip to content') }}</a>
    <header class="site-header">
      <div class="site-header-row">
        <button
          ref="menuButton"
          class="menu-toggle"
          type="button"
          :aria-expanded="menuOpen"
          aria-controls="main-navigation"
          :aria-label="$tr(menuOpen ? 'Close main menu' : 'Open main menu')"
          @click="menuOpen = !menuOpen"
        >
          <span aria-hidden="true" class="menu-toggle-lines"></span>
        </button>
        <a class="wordmark" href="/" :aria-label="$tr('Contestmaster home')">{{
          $tr('Contestmaster')
        }}</a>
        <span class="header-caption">{{
          $tr('Amateur radio contest engine')
        }}</span>
        <div class="header-actions">
          <div class="locale-picker">
            <label class="visually-hidden" for="application-locale">{{
              $tr('Language')
            }}</label>
            <select
              id="application-locale"
              :value="selectedLocale"
              @change="changeLocale"
            >
              <option lang="en" value="en">{{ $tr('English') }}</option>
              <option lang="de" value="de">{{ $tr('Deutsch') }}</option>
              <option lang="fr" value="fr">{{ $tr('Français') }}</option>
              <option lang="es" value="es">{{ $tr('Español') }}</option>
              <option lang="it" value="it">{{ $tr('Italiano') }}</option>
            </select>
          </div>
          <RouterLink class="header-upload-action" to="/submit-log">
            {{ $tr('Submit a log') }}
          </RouterLink>
          <RouterLink
            v-if="!participantSession"
            class="participant-header-action"
            to="/participant/access"
          >
            {{ $tr('Participant access') }}
          </RouterLink>
          <button
            v-else
            class="participant-header-action"
            type="button"
            :disabled="participantSigningOut"
            :aria-label="`${$tr('Log Off')} ${participantCallsign}`"
            @click="handleParticipantSignOut"
          >
            <span class="participant-header-callsign">{{
              participantCallsign
            }}</span>
            <span aria-hidden="true">·</span>
            {{ $tr(participantSigningOut ? 'Working…' : 'Log Off') }}
          </button>
        </div>
      </div>
      <nav
        id="main-navigation"
        :aria-label="$tr('Main navigation')"
        class="site-navigation"
        :class="{ 'is-open': menuOpen }"
        @click="closeMenu()"
      >
        <RouterLink to="/">{{ $tr('Published results') }}</RouterLink>
        <RouterLink to="/manage/contests">
          {{ $tr('Manage contests') }}
        </RouterLink>
        <RouterLink to="/manage/rulesets">
          {{ $tr('Manage rulesets') }}
        </RouterLink>
        <RouterLink to="/participant/access">
          {{ $tr('Participant access') }}
        </RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/master-data"
        >
          {{ $tr('Master data') }}
        </RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/users"
        >
          {{ $tr('System users') }}
        </RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/audit-log"
        >
          {{ $tr('Audit log') }}
        </RouterLink>
        <RouterLink
          v-if="staffUser?.role === 'global_administrator'"
          to="/admin/operating-catalog"
        >
          {{ $tr('Bands and modes') }}
        </RouterLink>
        <RouterLink v-if="!staffUser" to="/sign-in">
          {{ $tr('Staff sign-in') }}
        </RouterLink>
        <button
          v-else
          class="sign-out-button"
          type="button"
          @click="handleSignOut"
        >
          {{ $tr('Sign out {name}', { name: staffUser.display_name }) }}
        </button>
      </nav>
    </header>
    <p v-if="localeError" class="shell-error" role="alert">
      {{ $tr(localeError) }}
    </p>
    <p v-if="signOutError" class="shell-error" role="alert">
      {{ $tr(signOutError) }}
    </p>
    <p v-if="participantSignOutError" class="shell-error" role="alert">
      {{ $tr(participantSignOutError) }}
    </p>
    <main id="main-content" class="main-content">
      <RouterView />
    </main>
    <SiteFooter />
  </div>
</template>
