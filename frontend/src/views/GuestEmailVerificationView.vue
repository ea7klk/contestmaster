<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { verifyGuestEntryEmail } from '../api/logs'

const route = useRoute()
const router = useRouter()
const busy = ref(true)
const error = ref('')
const entryId = ref<number | null>(null)
const resultsEnabled = ref(false)
const canManageEntry = ref(false)

onMounted(async () => {
  const token = route.query.token
  if (typeof token !== 'string') {
    error.value = 'This verification link is missing its token.'
    busy.value = false
    return
  }
  try {
    const result = await verifyGuestEntryEmail(token)
    entryId.value = result.entry_id
    resultsEnabled.value = result.results_notifications_enabled
    if (result.entry_access_token) {
      canManageEntry.value = true
      sessionStorage.setItem(
        `contestmaster-entry-${result.entry_id}`,
        result.entry_access_token,
      )
    }
  } catch (reason) {
    error.value =
      reason instanceof ApiError
        ? reason.message
        : 'The email address could not be verified. Request a new link using your entry receipt.'
  } finally {
    await router.replace({ path: '/guest/email/verify' })
    busy.value = false
  }
})
</script>

<template>
  <section class="form-card" aria-labelledby="guest-email-verification-title">
    <p class="eyebrow">{{ $tr('Guest log access') }}</p>
    <h1 id="guest-email-verification-title">{{ $tr('Email verification') }}</h1>
    <p v-if="busy" role="status">{{ $tr('Verifying your email address…') }}</p>
    <p v-else-if="error" class="form-error" role="alert">{{ $tr(error) }}</p>
    <template v-else>
      <p role="status">{{ $tr('Your email address is verified.') }}</p>
      <p v-if="resultsEnabled">{{ $tr('You will receive a notice when public results are published. The message will link to the public standings.') }}</p>
      <p v-else>{{ $tr('Result publication notices were not selected for this address.') }}</p>
      <RouterLink
        v-if="entryId !== null && canManageEntry"
        class="primary-button"
        :to="`/entries/${entryId}/manage`"
      >
        {{ $tr('Manage this entry') }}
      </RouterLink>
    </template>
  </section>
</template>
