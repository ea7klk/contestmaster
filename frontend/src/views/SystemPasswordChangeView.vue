<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { changeSystemPassword } from '../api/identity'

const route = useRoute()
const router = useRouter()
const currentPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
const busy = ref(false)
const error = ref('')

function safeNextPath(): string {
  const candidate = typeof route.query.next === 'string' ? route.query.next : ''
  if (
    candidate.startsWith('/') &&
    !candidate.startsWith('//') &&
    !candidate.startsWith('/change-password')
  ) return candidate
  return '/manage/contests'
}

async function submit() {
  if (busy.value) return
  error.value = ''
  if (newPassword.value !== confirmation.value) {
    error.value = 'The new passwords do not match.'
    return
  }
  busy.value = true
  try {
    await changeSystemPassword(currentPassword.value, newPassword.value)
    await router.replace(safeNextPath())
  } catch (cause) {
    error.value = cause instanceof ApiError
      ? cause.message
      : 'Your password could not be changed. Please try again.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="welcome-card password-change-card" aria-labelledby="password-change-heading">
    <p class="eyebrow">{{ $tr('Account security') }}</p>
    <h1 id="password-change-heading">{{ $tr('Change your password') }}</h1>
    <p class="intro">{{ $tr('Your administrator requires you to choose a new password before you can continue.') }}</p>
    <p v-if="error" class="error-panel" role="alert">{{ $tr(error) }}</p>
    <form class="stacked-form" @submit.prevent="submit">
      <label for="current-password">{{ $tr('Current password') }}<input id="current-password" v-model="currentPassword" type="password" autocomplete="current-password" required /></label>
      <label for="new-password">{{ $tr('New password') }}<input id="new-password" v-model="newPassword" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required /></label>
      <label for="confirm-password">{{ $tr('Confirm new password') }}<input id="confirm-password" v-model="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required /></label>
      <button class="primary-button" type="submit" :disabled="busy">{{ busy ? $tr('Saving password…') : $tr('Save new password') }}</button>
    </form>
  </section>
</template>

<style scoped>
.password-change-card {
  width: 100%;
  max-width: 40rem;
  margin-inline: auto;
}

.stacked-form {
  display: grid;
  gap: 1rem;
  margin-top: 1.5rem;
}

.stacked-form label {
  display: grid;
  gap: 0.4rem;
  font-weight: 650;
}

.stacked-form input {
  width: 100%;
  min-width: 0;
}

.error-panel {
  margin: 0;
  padding: 0.75rem;
  border: 1px solid var(--color-error-border);
  border-radius: 0.45rem;
  color: var(--color-error-ink);
  background: var(--color-error-surface);
}

.primary-button {
  min-height: 2.75rem;
  padding: 0.6rem 0.9rem;
  border: 0;
  border-radius: 0.45rem;
  color: var(--color-surface);
  background: var(--color-brand-700);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.primary-button:disabled {
  opacity: 0.65;
  cursor: wait;
}
</style>
