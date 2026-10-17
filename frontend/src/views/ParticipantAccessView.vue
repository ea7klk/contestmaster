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
  promoteParticipantCallsign,
  removeParticipantCallsign,
  updateParticipantProfile,
  requestParticipantEmailChange,
  confirmParticipantEmailChange,
  withdrawParticipantEntry,
  getParticipantEntries,
  requestParticipantMagicLink,
  signOutParticipant,
  claimParticipantEntries,
  type ParticipantEntry,
} from '../api/participantIdentity'
import { formatUtcDateTime } from '../i18n'
import {
  participantSession,
  setParticipantSession,
} from '../state/participantSession'

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
const profileCallsigns = ref<
  Array<{ id: number; callsign: string; is_primary: boolean }>
>([])
const profileName = ref('')
const newEmail = ref('')
const claimReceipt = ref('')
const claimSuccess = ref<{ callsign: string; count: number } | null>(null)

async function requestLink() {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await requestParticipantMagicLink(email.value)
    message.value =
      'If this address can be used, a sign-in email will arrive shortly. Check your inbox.'
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
      await registerParticipant({
        email: email.value,
        callsign: callsign.value,
        password: password.value,
        display_name: displayName.value || undefined,
      })
      message.value = 'A verification email will arrive shortly to activate your account.'
    } else if (mode.value === 'login') {
      await loginParticipant(email.value, password.value)
      await router.replace('/participant/entries')
      await loadEntries()
    } else if (mode.value === 'reset') {
      const token =
        typeof route.query.token === 'string' ? route.query.token : ''
      await resetParticipantPassword(token, password.value)
      message.value = 'Your password has been updated. You can now sign in.'
      mode.value = 'login'
    } else {
      await requestParticipantPasswordReset(email.value)
      message.value =
        'If the account is eligible, a password reset email will arrive shortly.'
    }
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The account request could not be completed.'
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
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The callsign could not be added.'
  } finally {
    busy.value = false
  }
}

async function removeCallsign(item: {
  id: number
  callsign: string
  is_primary: boolean
}) {
  busy.value = true
  error.value = ''
  try {
    await removeParticipantCallsign(item.id)
    profileCallsigns.value = profileCallsigns.value.filter(
      (candidate) => candidate.id !== item.id,
    )
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The callsign could not be removed.'
  } finally {
    busy.value = false
  }
}

async function promoteCallsign(item: { id: number; callsign: string }) {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const promoted = await promoteParticipantCallsign(item.id)
    profileCallsigns.value = profileCallsigns.value.map((candidate) => ({
      ...candidate,
      is_primary: candidate.id === promoted.id,
    }))
    if (participantSession.value) {
      setParticipantSession({
        ...participantSession.value,
        callsigns: profileCallsigns.value,
      })
    }
    message.value = 'Primary callsign updated.'
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The primary callsign could not be changed.'
  } finally {
    busy.value = false
  }
}

async function saveProfile() {
  busy.value = true
  error.value = ''
  try {
    const profile = await updateParticipantProfile(
      profileName.value.trim() || null,
    )
    profileName.value = profile.display_name ?? ''
    message.value = 'Profile changes saved.'
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Profile changes could not be saved.'
  } finally {
    busy.value = false
  }
}

async function changeEmail() {
  busy.value = true
  error.value = ''
  try {
    await requestParticipantEmailChange(newEmail.value)
    message.value = 'Confirmation emails will be sent shortly to both addresses.'
    newEmail.value = ''
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The email change could not be started.'
  } finally {
    busy.value = false
  }
}

async function claimGuestLogs() {
  busy.value = true
  error.value = ''
  message.value = ''
  claimSuccess.value = null
  try {
    const result = await claimParticipantEntries(claimReceipt.value.trim())
    claimReceipt.value = ''
    claimSuccess.value = {
      callsign: result.callsign,
      count: result.claimed_entries,
    }
    await loadEntries()
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Guest logs could not be claimed. Check the receipt token and try again.'
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
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The entry could not be withdrawn.'
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
    setParticipantSession(profile)
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
    setParticipantSession(null)
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
    if (!token) {
      error.value = 'This email confirmation link is missing its token.'
      return
    }
    try {
      await confirmParticipantEmailChange(token)
      message.value =
        'Email confirmation recorded. The change completes after both addresses are confirmed.'
    } catch {
      error.value = 'This email confirmation link could not be verified.'
    }
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
  <section
    class="page-card participant-access-card"
    :class="{ 'is-signed-in': signedIn }"
    aria-labelledby="participant-access-heading"
  >
    <header class="participant-page-heading">
      <p class="eyebrow">{{ $tr('Participant access') }}</p>
      <h1 id="participant-access-heading">
        {{
          $tr(
            mode === 'register'
              ? 'Create account'
              : mode === 'login'
                ? 'Password sign-in'
                : mode === 'reset'
                  ? 'Reset password'
                  : 'Participant access',
          )
        }}
      </h1>
    </header>
    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <p v-if="message" role="status" class="success-panel">
      {{ $tr(message) }}
    </p>
    <p v-if="claimSuccess" role="status" class="success-panel">
      {{
        $tr('Guest logs linked to {callsign}: {count}.', {
          callsign: claimSuccess.callsign,
          count: claimSuccess.count,
        })
      }}
    </p>

    <div v-if="signedIn" class="participant-dashboard">
      <h2>{{ $tr('Your callsigns') }}</h2>
      <form class="inline-form" @submit.prevent="saveProfile">
        <label for="participant-display-name-edit">{{
          $tr('Display name')
        }}</label>
        <input
          id="participant-display-name-edit"
          v-model.trim="profileName"
          maxlength="160"
          autocomplete="name"
        />
        <button class="secondary-button" type="submit" :disabled="busy">
          {{ $tr('Save profile') }}
        </button>
      </form>
      <ul class="participant-callsigns">
        <li v-for="item in profileCallsigns" :key="item.id">
          <span>
            <strong>{{ item.callsign }}</strong>
            <span v-if="item.is_primary" class="participant-primary-label">
              {{ $tr('Primary') }}
            </span>
          </span>
          <div v-if="!item.is_primary" class="participant-callsign-actions">
            <button
              type="button"
              class="text-button"
              :disabled="busy"
              @click="promoteCallsign(item)"
            >
              {{ $tr('Set as primary') }}
            </button>
            <button
              type="button"
              class="text-button"
              :disabled="busy"
              @click="removeCallsign(item)"
            >
              {{ $tr('Remove') }}
            </button>
          </div>
        </li>
      </ul>
      <form class="inline-form" @submit.prevent="addCallsign">
        <label for="new-callsign">{{ $tr('Add another callsign') }}</label>
        <input
          id="new-callsign"
          v-model.trim="callsign"
          required
          maxlength="32"
        />
        <button class="secondary-button" type="submit" :disabled="busy">
          {{ $tr('Add callsign') }}
        </button>
      </form>
      <form class="inline-form" @submit.prevent="changeEmail">
        <label for="new-participant-email">{{
          $tr('Change account email')
        }}</label>
        <input
          id="new-participant-email"
          v-model.trim="newEmail"
          type="email"
          required
          maxlength="320"
          autocomplete="email"
        />
        <button class="secondary-button" type="submit" :disabled="busy">
          {{ $tr('Send confirmations') }}
        </button>
      </form>
      <section
        class="claim-guest-logs"
        aria-labelledby="claim-guest-logs-heading"
      >
        <h2 id="claim-guest-logs-heading">{{ $tr('Claim guest logs') }}</h2>
        <p class="participant-help">
          {{
            $tr(
              'Enter the entry receipt token from a guest log submitted with one of your callsigns. The token proves access to that entry; matching guest logs for that callsign will be added to your account.',
            )
          }}
        </p>
        <form
          id="claim-guest-logs-form"
          class="inline-form"
          @submit.prevent="claimGuestLogs"
        >
          <label for="guest-entry-receipt">{{
            $tr('Entry receipt token')
          }}</label>
          <input
            id="guest-entry-receipt"
            v-model="claimReceipt"
            type="password"
            required
            minlength="20"
            maxlength="200"
            autocomplete="off"
          />
          <button class="secondary-button" type="submit" :disabled="busy">
            {{ $tr('Claim logs') }}
          </button>
        </form>
      </section>
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
        <table class="participant-entries-table">
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
              <td>
                <span class="participant-entry-status">{{ entry.status }}</span>
              </td>
              <td>{{ formatUtcDateTime(entry.submitted_at) }}</td>
              <td>
                <RouterLink
                  class="secondary-button"
                  :to="`/entries/${entry.id}/manage`"
                >
                  {{ $tr('Manage entry') }}
                </RouterLink>
                <button
                  v-if="entry.status !== 'withdrawn'"
                  type="button"
                  class="text-button"
                  :disabled="busy"
                  @click="withdrawEntry(entry.id)"
                >
                  {{ $tr('Withdraw entry') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <form
      v-else
      class="stacked-form participant-auth-form"
      @submit.prevent="mode === 'magic' ? requestLink() : submitIdentity()"
    >
      <div
        v-if="route.path !== '/participant/reset-password'"
        class="identity-modes"
        role="group"
        :aria-label="$tr('Participant account options')"
      >
        <button
          type="button"
          class="secondary-button participant-mode-button"
          :class="{ 'is-active': mode === 'magic' }"
          :aria-pressed="mode === 'magic'"
          :disabled="busy"
          @click="mode = 'magic'"
        >
          {{ $tr('Email link') }}
        </button>
        <button
          type="button"
          class="secondary-button participant-mode-button"
          :class="{ 'is-active': mode === 'login' }"
          :aria-pressed="mode === 'login'"
          :disabled="busy"
          @click="mode = 'login'"
        >
          {{ $tr('Password sign-in') }}
        </button>
        <button
          type="button"
          class="secondary-button participant-mode-button"
          :class="{ 'is-active': mode === 'register' }"
          :aria-pressed="mode === 'register'"
          :disabled="busy"
          @click="mode = 'register'"
        >
          {{ $tr('Create account') }}
        </button>
      </div>
      <p class="participant-auth-intro">
        {{
          $tr(
            mode === 'register'
              ? 'Registration is optional. Create an account with your email, callsign, and password, then verify your email before signing in. You can submit logs as a guest at any time.'
              : mode === 'login'
                ? 'Sign in to manage your account and entries.'
                : mode === 'reset'
                  ? 'Choose a new password for your account.'
                  : mode === 'forgot'
                    ? 'Enter your account email to receive a password reset link.'
                    : 'Enter your verified participant email address to receive a short-lived sign-in link.',
          )
        }}
      </p>
      <label v-if="mode !== 'reset'" for="participant-email">{{
        $tr('Email address')
      }}</label>
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
      <label v-if="mode === 'register'" for="participant-callsign">{{
        $tr('Callsign')
      }}</label>
      <input
        v-if="mode === 'register'"
        id="participant-callsign"
        v-model.trim="callsign"
        required
        maxlength="32"
        autocomplete="off"
      />
      <label v-if="mode === 'register'" for="participant-display-name">{{
        $tr('Display name (optional)')
      }}</label>
      <input
        v-if="mode === 'register'"
        id="participant-display-name"
        v-model.trim="displayName"
        maxlength="160"
        autocomplete="name"
      />
      <label
        v-if="['register', 'login', 'reset'].includes(mode)"
        for="participant-password"
        >{{ $tr(mode === 'reset' ? 'New password' : 'Password') }}</label
      >
      <input
        v-if="['register', 'login', 'reset'].includes(mode)"
        id="participant-password"
        v-model="password"
        type="password"
        :required="mode !== 'magic'"
        minlength="12"
        :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
      />
      <button
        class="primary-button participant-submit-button"
        type="submit"
        :disabled="busy"
      >
        {{
          busy
            ? $tr('Working…')
            : mode === 'register'
              ? $tr('Create account and send verification link')
              : mode === 'login'
                ? $tr('Sign in')
                : mode === 'reset'
                  ? $tr('Save new password')
                  : mode === 'forgot'
                    ? $tr('Send password reset link')
                    : $tr('Email me a sign-in link')
        }}
      </button>
      <button
        v-if="mode === 'magic' || mode === 'login'"
        type="button"
        class="text-button"
        :disabled="busy"
        @click="mode = 'forgot'"
      >
        {{ $tr('Forgot password?') }}
      </button>
      <button
        v-if="mode === 'forgot'"
        type="button"
        class="text-button"
        :disabled="busy"
        @click="mode = 'login'"
      >
        {{ $tr('Back to sign-in') }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.participant-access-card {
  max-width: 40rem;
}

.participant-access-card.is-signed-in {
  max-width: 72rem;
}

.participant-page-heading h1 {
  margin-top: 0.4rem;
}

.participant-auth-form {
  gap: 0.85rem;
  margin-top: 0;
}

.participant-auth-intro,
.participant-help {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.6;
}

.participant-auth-intro {
  padding: 0.85rem 1rem;
  border-left: 3px solid var(--color-accent);
  border-radius: 0.2rem 0.5rem 0.5rem 0.2rem;
  background: var(--color-brand-wash);
}

.identity-modes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
  padding: 0.35rem;
  border: 1px solid var(--color-border);
  border-radius: 0.7rem;
  background: var(--color-surface-muted);
}

.participant-mode-button {
  width: 100%;
  min-height: 2.8rem;
  border-color: transparent;
  text-align: center;
}

.participant-mode-button:hover:not(:disabled) {
  border-color: var(--color-brand-line);
  background: var(--color-brand-wash-strong);
}

.participant-mode-button.is-active,
.participant-mode-button.is-active:hover {
  border-color: var(--color-brand-800);
  color: var(--color-surface);
  background: var(--color-brand-800);
}

.participant-mode-button:disabled,
.primary-button:disabled,
.secondary-button:disabled,
.text-button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.participant-auth-form label {
  display: grid;
  gap: 0.35rem;
  font-weight: 650;
}

.participant-auth-form input {
  width: 100%;
}

.primary-button,
.secondary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 2.6rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-brand-700);
  background: var(--color-surface);
  font: inherit;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}

.primary-button {
  border-color: transparent;
  color: var(--color-surface);
  background: var(--color-brand-700);
}

.primary-button:hover:not(:disabled) {
  background: var(--color-brand-800);
}

.secondary-button:hover:not(:disabled) {
  border-color: var(--color-brand-700);
  color: var(--color-brand-900);
  background: var(--color-brand-wash);
}

.participant-submit-button {
  width: 100%;
  min-height: 2.9rem;
  margin-top: 0.25rem;
}

.text-button {
  width: fit-content;
  padding: 0.35rem 0.2rem;
  border: 0;
  color: var(--color-brand-700);
  background: transparent;
  font-weight: 650;
  text-align: left;
  text-decoration: underline;
  text-underline-offset: 0.18em;
  cursor: pointer;
}

.text-button:hover:not(:disabled) {
  color: var(--color-brand-900);
}

.participant-dashboard {
  display: grid;
  gap: 1.5rem;
}

.participant-dashboard h2 {
  margin: 0;
}

.section-heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.participant-dashboard ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.inline-form {
  display: grid;
  grid-template-columns: minmax(9rem, 0.8fr) minmax(0, 1.6fr) auto;
  align-items: end;
  gap: 0.75rem;
  padding: 0.95rem;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface);
}

.inline-form label {
  display: grid;
  gap: 0.35rem;
  font-weight: 650;
}

.inline-form input {
  width: 100%;
}

.participant-callsigns {
  display: grid;
  gap: 0.45rem;
}

.participant-callsigns li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  background: var(--color-brand-wash);
}

.participant-callsign-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
}

.participant-primary-label,
.participant-entry-status {
  display: inline-flex;
  align-items: center;
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  color: var(--color-brand-800);
  background: var(--color-brand-wash-strong);
  font-size: 0.8rem;
  font-weight: 700;
}

.participant-primary-label {
  margin-left: 0.4rem;
}

.claim-guest-logs {
  display: grid;
  gap: 0.85rem;
  padding: 1rem;
  border: 1px solid var(--color-brand-line);
  border-radius: 0.65rem;
  background: var(--color-brand-wash);
}

.claim-guest-logs h2 {
  font-size: 1.2rem;
}

.participant-entries-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.participant-entries-table th,
.participant-entries-table td {
  padding: 0.7rem 0.8rem;
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.participant-entries-table th {
  color: var(--color-brand-900);
  background: var(--color-surface-muted);
  font-size: 0.88rem;
}

.participant-entries-table td:last-child {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.participant-entries-table .secondary-button {
  min-height: 2.25rem;
  padding: 0.35rem 0.6rem;
  font-size: 0.88rem;
}

@media (max-width: 700px) {
  .identity-modes {
    grid-template-columns: 1fr;
  }

  .participant-mode-button {
    justify-content: flex-start;
    text-align: left;
  }

  .inline-form {
    grid-template-columns: 1fr;
  }

  .inline-form .secondary-button {
    width: 100%;
  }

  .participant-entries-table th,
  .participant-entries-table td {
    padding: 0.55rem;
  }
}
</style>
