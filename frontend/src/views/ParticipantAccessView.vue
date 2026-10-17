<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import {
  consumeParticipantMagicLink,
  registerParticipant,
  loginParticipant,
  requestParticipantPasswordReset,
  resetParticipantPassword,
  getParticipantProfile,
  addParticipantCallsign,
  removeParticipantCallsign,
  updateParticipantProfile,
  requestParticipantEmailChange,
  confirmParticipantEmailChange,
  withdrawParticipantEntry,
  getParticipantEntries,
  requestParticipantMagicLink,
  signOutParticipant,
  type ParticipantEntry,
} from '../api/participantIdentity'
import { formatUtcDateTime } from '../i18n'

const route = useRoute()
const router = useRouter()
const email = ref('')
const entries = ref<ParticipantEntry[]>([])
const busy = ref(false)
const message = ref('')
const error = ref('')
const signedIn = ref(false)
const mode = ref<'magic' | 'login' | 'register' | 'reset' | 'forgot'>('magic')
const callsign = ref('')
const password = ref('')
const displayName = ref('')
const profileCallsigns = ref<Array<{ id: number; callsign: string; is_primary: boolean }>>([])
const profileName = ref('')
const newEmail = ref('')

async function requestLink() {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await requestParticipantMagicLink(email.value)
    message.value =
      'If this address can be used, a one-time sign-in link has been sent. Check your email.'
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The sign-in link could not be requested.'
  } finally {
    busy.value = false
  }
}

async function submitIdentity() {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    if (mode.value === 'register') {
      await registerParticipant({ email: email.value, callsign: callsign.value, password: password.value, display_name: displayName.value || undefined })
      message.value = 'Check your email for a verification link to activate the account.'
    } else if (mode.value === 'login') {
      await loginParticipant(email.value, password.value)
      await router.replace('/participant/entries')
      await loadEntries()
    } else if (mode.value === 'reset') {
      const token = typeof route.query.token === 'string' ? route.query.token : ''
      await resetParticipantPassword(token, password.value)
      message.value = 'Your password has been updated. You can now sign in.'
      mode.value = 'login'
    } else {
      await requestParticipantPasswordReset(email.value)
      message.value = 'If the account is eligible, a password reset link was sent.'
    }
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : 'The account request could not be completed.'
  } finally {
    busy.value = false
  }
}

async function addCallsign() {
  busy.value = true
  error.value = ''
  try {
    const item = await addParticipantCallsign(callsign.value)
    profileCallsigns.value.push(item)
    callsign.value = ''
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : 'The callsign could not be added.'
  } finally {
    busy.value = false
  }
}

async function removeCallsign(item: { id: number; callsign: string; is_primary: boolean }) {
  busy.value = true
  error.value = ''
  try {
    await removeParticipantCallsign(item.id)
    profileCallsigns.value = profileCallsigns.value.filter((candidate) => candidate.id !== item.id)
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'The callsign could not be removed.' }
  finally { busy.value = false }
}

async function saveProfile() {
  busy.value = true
  error.value = ''
  try {
    const profile = await updateParticipantProfile(profileName.value.trim() || null)
    profileName.value = profile.display_name ?? ''
    message.value = 'Profile changes saved.'
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'Profile changes could not be saved.' }
  finally { busy.value = false }
}

async function changeEmail() {
  busy.value = true
  error.value = ''
  try {
    await requestParticipantEmailChange(newEmail.value)
    message.value = 'Confirmation links have been sent to both email addresses.'
    newEmail.value = ''
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : 'The email change could not be started.'
  } finally {
    busy.value = false
  }
}

async function withdrawEntry(entryId: number) {
  busy.value = true
  error.value = ''
  try {
    await withdrawParticipantEntry(entryId)
    await loadEntries()
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : 'The entry could not be withdrawn.'
  } finally {
    busy.value = false
  }
}

async function loadEntries() {
  busy.value = true
  error.value = ''
  try {
    const result = await getParticipantEntries()
    entries.value = result.items
    const profile = await getParticipantProfile()
    profileCallsigns.value = profile.callsigns ?? []
    profileName.value = profile.display_name ?? ''
    signedIn.value = true
  } catch (cause) {
    signedIn.value = false
    if (!(cause instanceof ApiError && cause.statusCode === 401)) {
      error.value =
        cause instanceof ApiError
          ? cause.message
          : 'Entries could not be loaded.'
    }
  } finally {
    busy.value = false
  }
}

async function handleSignOut() {
  busy.value = true
  error.value = ''
  try {
    await signOutParticipant()
    signedIn.value = false
    entries.value = []
    await router.replace('/participant/access')
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Participant sign-out could not be completed.'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  if (route.path === '/participant/reset-password') {
    mode.value = 'reset'
    return
  }
  if (route.path === '/participant/confirm-email-change') {
    const token = typeof route.query.token === 'string' ? route.query.token : ''
    if (!token) { error.value = 'This email confirmation link is missing its token.'; return }
    try {
      await confirmParticipantEmailChange(token)
      message.value = 'Email confirmation recorded. The change completes after both addresses are confirmed.'
    } catch { error.value = 'This email confirmation link could not be verified.' }
    return
  }
  if (route.path === '/participant/verify') {
    const token = typeof route.query.token === 'string' ? route.query.token : ''
    if (!token) {
      error.value =
        'This sign-in link is missing its token. Request a new link.'
      return
    }
    busy.value = true
    try {
      await consumeParticipantMagicLink(token)
      await router.replace('/participant/entries')
      await loadEntries()
    } catch (cause) {
      error.value =
        cause instanceof ApiError
          ? cause.message
          : 'This sign-in link could not be verified. Request a new link.'
    } finally {
      busy.value = false
    }
  } else if (route.path === '/participant/entries') {
    await loadEntries()
  }
})
</script>

<template>
  <section class="page-card" aria-labelledby="participant-access-heading">
    <h1 id="participant-access-heading">{{ $tr('Participant access') }}</h1>
    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <p v-if="message" role="status">{{ $tr(message) }}</p>

    <div v-if="signedIn">
      <h2>{{ $tr('Your callsigns') }}</h2>
      <form class="inline-form" @submit.prevent="saveProfile">
        <label for="participant-display-name-edit">{{ $tr('Display name') }}</label>
        <input id="participant-display-name-edit" v-model.trim="profileName" maxlength="160" autocomplete="name" />
        <button class="secondary-button" type="submit" :disabled="busy">{{ $tr('Save profile') }}</button>
      </form>
      <ul><li v-for="item in profileCallsigns" :key="item.id">{{ item.callsign }} <span v-if="item.is_primary">({{ $tr('Primary') }})</span><button v-if="!item.is_primary" type="button" class="text-button" :disabled="busy" @click="removeCallsign(item)">{{ $tr('Remove') }}</button></li></ul>
      <form class="inline-form" @submit.prevent="addCallsign">
        <label for="new-callsign">{{ $tr('Add another callsign') }}</label>
        <input id="new-callsign" v-model.trim="callsign" required maxlength="32" />
        <button class="secondary-button" type="submit" :disabled="busy">{{ $tr('Add callsign') }}</button>
      </form>
      <form class="inline-form" @submit.prevent="changeEmail">
        <label for="new-participant-email">{{ $tr('Change account email') }}</label>
        <input id="new-participant-email" v-model.trim="newEmail" type="email" required maxlength="320" autocomplete="email" />
        <button class="secondary-button" type="submit" :disabled="busy">{{ $tr('Send confirmations') }}</button>
      </form>
      <div class="section-heading-row">
        <h2>{{ $tr('Your entries') }}</h2>
        <button
          class="secondary-button"
          type="button"
          :disabled="busy"
          @click="handleSignOut"
        >
          {{ $tr('Sign out') }}
        </button>
      </div>
      <p v-if="entries.length === 0">
        {{ $tr('There are no entries associated with this email yet.') }}
      </p>
      <div v-else class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{{ $tr('Contest') }}</th>
              <th>{{ $tr('Entry') }}</th>
              <th>{{ $tr('Status') }}</th>
              <th>{{ $tr('Submitted') }}</th>
              <th>{{ $tr('Actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in entries" :key="entry.id">
              <td>{{ entry.contest_name }}</td>
              <td>{{ entry.entry_key }}</td>
              <td>{{ entry.status }}</td>
              <td>{{ formatUtcDateTime(entry.submitted_at) }}</td>
              <td>
                <RouterLink :to="`/entries/${entry.id}/manage`">
                  {{ $tr('Manage entry') }}
                </RouterLink>
                <button v-if="entry.status !== 'withdrawn'" type="button" class="text-button" :disabled="busy" @click="withdrawEntry(entry.id)">{{ $tr('Withdraw entry') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <form v-else class="stacked-form" @submit.prevent="mode === 'magic' ? requestLink() : submitIdentity()">
      <div v-if="route.path !== '/participant/reset-password'" class="identity-modes" role="group" :aria-label="$tr('Participant account options')">
        <button type="button" @click="mode = 'magic'">{{ $tr('Email link') }}</button>
        <button type="button" @click="mode = 'login'">{{ $tr('Password sign-in') }}</button>
        <button type="button" @click="mode = 'register'">{{ $tr('Create account') }}</button>
      </div>
      <p>
        {{
          $tr(mode === 'register' ? 'Register with your email, callsign, and password. You must verify the email before signing in.' : mode === 'login' ? 'Sign in to manage your account and entries.' : mode === 'reset' ? 'Choose a new password for your account.' : mode === 'forgot' ? 'Enter your account email to receive a password reset link.' :
            'Enter your verified participant email address to receive a short-lived sign-in link.',
          )
        }}
      </p>
      <label v-if="mode !== 'reset'" for="participant-email">{{ $tr('Email address') }}</label>
      <input
        v-if="mode !== 'reset'"
        id="participant-email"
        v-model.trim="email"
        name="email"
        type="email"
        autocomplete="email"
        required
        maxlength="320"
      />
      <label v-if="mode === 'register'" for="participant-callsign">{{ $tr('Callsign') }}</label>
      <input v-if="mode === 'register'" id="participant-callsign" v-model.trim="callsign" required maxlength="32" autocomplete="off" />
      <label v-if="mode === 'register'" for="participant-display-name">{{ $tr('Display name (optional)') }}</label>
      <input v-if="mode === 'register'" id="participant-display-name" v-model.trim="displayName" maxlength="160" autocomplete="name" />
      <label v-if="['register', 'login', 'reset'].includes(mode)" for="participant-password">{{ $tr(mode === 'reset' ? 'New password' : 'Password') }}</label>
      <input v-if="['register', 'login', 'reset'].includes(mode)" id="participant-password" v-model="password" type="password" :required="mode !== 'magic'" minlength="12" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" />
      <button class="primary-button" type="submit" :disabled="busy">
        {{ busy ? $tr('Working…') : mode === 'register' ? $tr('Create account and send verification link') : mode === 'login' ? $tr('Sign in') : mode === 'reset' ? $tr('Save new password') : mode === 'forgot' ? $tr('Send password reset link') : $tr('Email me a sign-in link') }}
      </button>
      <button v-if="mode === 'magic' || mode === 'login'" type="button" class="text-button" @click="mode = 'forgot'">{{ $tr('Forgot password?') }}</button>
      <button v-if="mode === 'forgot'" type="button" class="text-button" @click="mode = 'login'">{{ $tr('Back to sign-in') }}</button>
    </form>
  </section>
</template>
