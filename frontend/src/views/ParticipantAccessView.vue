<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import {
  consumeParticipantMagicLink,
  getParticipantEntries,
  requestParticipantMagicLink,
  signOutParticipant,
  type ParticipantEntry,
} from '../api/participantIdentity'

const route = useRoute()
const router = useRouter()
const email = ref('')
const entries = ref<ParticipantEntry[]>([])
const busy = ref(false)
const message = ref('')
const error = ref('')
const signedIn = ref(false)

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

async function loadEntries() {
  busy.value = true
  error.value = ''
  try {
    const result = await getParticipantEntries()
    entries.value = result.items
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
    <h1 id="participant-access-heading">Participant access</h1>
    <p v-if="error" role="alert" class="form-error">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>

    <div v-if="signedIn">
      <div class="section-heading-row">
        <h2>Your entries</h2>
        <button
          class="secondary-button"
          type="button"
          :disabled="busy"
          @click="handleSignOut"
        >
          Sign out
        </button>
      </div>
      <p v-if="entries.length === 0">
        There are no entries associated with this email yet.
      </p>
      <div v-else class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Contest</th>
              <th>Entry</th>
              <th>Status</th>
              <th>Submitted</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in entries" :key="entry.id">
              <td>{{ entry.contest_name }}</td>
              <td>{{ entry.entry_key }}</td>
              <td>{{ entry.status }}</td>
              <td>{{ new Date(entry.submitted_at).toLocaleString() }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <form v-else class="stacked-form" @submit.prevent="requestLink">
      <p>
        Enter your verified participant email address to receive a short-lived
        sign-in link.
      </p>
      <label for="participant-email">Email address</label>
      <input
        id="participant-email"
        v-model.trim="email"
        name="email"
        type="email"
        autocomplete="email"
        required
        maxlength="320"
      />
      <button class="primary-button" type="submit" :disabled="busy">
        {{ busy ? 'Sending…' : 'Email me a sign-in link' }}
      </button>
    </form>
  </section>
</template>
