<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { signIn } from '../api/identity'

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')
const router = useRouter()
const route = useRoute()

async function submit() {
  if (submitting.value) return
  submitting.value = true
  errorMessage.value = ''
  try {
    await signIn(email.value.trim(), password.value)
    await router.replace(
      typeof route.query.next === 'string' &&
        route.query.next.startsWith('/') &&
        !route.query.next.startsWith('//')
        ? route.query.next
        : '/manage/contests',
    )
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : 'Sign-in failed. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="welcome-card auth-card" aria-labelledby="sign-in-title">
    <p class="eyebrow">{{ $tr('Contest staff') }}</p>
    <h1 id="sign-in-title">{{ $tr('Sign in') }}</h1>
    <p class="intro">
      {{
        $tr('Use your Contestmaster administrator or contest-manager account.')
      }}
    </p>

    <form class="stacked-form" @submit.prevent="submit">
      <label>
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
      <label>
        {{ $tr('Password') }}
        <input
          v-model="password"
          autocomplete="current-password"
          name="password"
          type="password"
          required
          maxlength="1024"
        />
      </label>
      <p v-if="errorMessage" class="error-panel" role="alert">
        {{ errorMessage }}
      </p>
      <button class="primary-button" type="submit" :disabled="submitting">
        {{ submitting ? 'Signing in…' : 'Sign in' }}
      </button>
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
