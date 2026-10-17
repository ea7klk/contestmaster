<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { requestSystemPasswordReset, resetSystemPassword, signIn } from '../api/identity'

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const message = ref('')
const mode = ref<'login' | 'forgot' | 'reset'>('login')
const router = useRouter()
const route = useRoute()

async function submit() {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  message.value = ''
  try {
    if (mode.value === 'forgot') {
      const result = await requestSystemPasswordReset(email.value.trim())
      message.value = result.message
    } else if (mode.value === 'reset') {
      const token = typeof route.query.token === 'string' ? route.query.token : ''
      await resetSystemPassword(token, password.value)
      message.value = 'Your password has been updated. You can now sign in.'
      mode.value = 'login'
    } else {
      const result = await signIn(email.value.trim(), password.value)
      const requestedPath = typeof route.query.next === 'string' &&
        route.query.next.startsWith('/') &&
        !route.query.next.startsWith('//') &&
        !route.query.next.startsWith('/change-password')
        ? route.query.next
        : '/manage/contests'
      await router.replace(
        result.user.must_change_password
          ? { path: '/change-password', query: { next: requestedPath } }
          : requestedPath,
      )
    }
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : 'Sign-in failed. Please try again.'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  if (route.path === '/reset-password') mode.value = 'reset'
})
</script>

<template>
  <section class="welcome-card auth-card" aria-labelledby="sign-in-title">
    <p class="eyebrow">{{ $tr('Contest staff') }}</p>
    <h1 id="sign-in-title">{{ $tr(mode === 'reset' ? 'Reset password' : mode === 'forgot' ? 'Recover password' : 'Sign in') }}</h1>
    <p class="intro">
      {{
        $tr(mode === 'login' ? 'Use your Contestmaster administrator or contest-manager account.' : mode === 'forgot' ? 'Enter your account email to receive a one-time password reset link.' : 'Choose a new password for your account.')
      }}
    </p>
    <p v-if="message" role="status">{{ $tr(message) }}</p>

    <form class="stacked-form" @submit.prevent="submit">
      <label v-if="mode !== 'reset'">
        {{ $tr('Email address') }}
        <input
          v-model="email"
          autocomplete="username"
          name="email"
          type="email"
          required
          maxlength="320"
        />
      </label>
      <label v-if="mode !== 'forgot'">
        {{ $tr('Password') }}
        <input
          v-model="password"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          name="password"
          type="password"
          required
          minlength="12"
          maxlength="1024"
        />
      </label>
      <p v-if="errorMessage" class="error-panel" role="alert">
        {{ errorMessage }}
      </p>
      <button class="primary-button" type="submit" :disabled="submitting">
        {{ submitting ? 'Working…' : mode === 'forgot' ? 'Send reset link' : mode === 'reset' ? 'Save new password' : 'Sign in' }}
      </button>
      <button v-if="mode === 'login'" type="button" class="text-button" @click="mode = 'forgot'; errorMessage = ''; message = ''">{{ $tr('Forgot password?') }}</button>
      <button v-if="mode === 'forgot'" type="button" class="text-button" @click="mode = 'login'">{{ $tr('Back to sign-in') }}</button>
    </form>
  </section>
</template>

<style scoped>
.auth-card {
  max-width: 34rem;
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
  min-height: 2.75rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  font: inherit;
}
.error-panel {
  margin: 0;
  padding: 0.75rem;
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
