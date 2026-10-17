<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import {
  listSubmittableContests,
  newIdempotencyKey,
  resendGuestEntryEmailVerification,
  setGuestEntryEmail,
  uploadContestLog,
  type ImportMessage,
  type LogSubmissionResult,
  type SubmitContest,
} from '../api/logs'

const contests = ref<SubmitContest[]>([])
const contestSlug = ref('')
const selectedContest = computed(() =>
  contests.value.find((item) => item.slug === contestSlug.value),
)
const acceptedFormats = computed(
  () => selectedContest.value?.accepted_formats ?? [],
)
const acceptedExtensions = computed(() =>
  acceptedFormats.value.flatMap((format) =>
    format === 'cabrillo'
      ? ['.log', '.cbr', '.cabrillo', '.txt']
      : format === 'adif'
        ? ['.adi', '.adif']
        : [],
  ),
)
const fileAccept = computed(() => acceptedExtensions.value.join(','))
const fileLabel = computed(() => {
  const formats = acceptedFormats.value
  if (formats.includes('adif') && formats.includes('cabrillo'))
    return 'Cabrillo or ADI/ADIF file'
  if (formats.includes('adif')) return 'ADI/ADIF file'
  if (formats.includes('cabrillo')) return 'Cabrillo file'
  return 'Log file'
})
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFileAllowed = computed(() => {
  if (!file.value) return true
  const extension = file.value.name
    .slice(file.value.name.lastIndexOf('.'))
    .toLowerCase()
  const format = ['.adi', '.adif'].includes(extension)
    ? 'adif'
    : ['.log', '.cbr', '.cabrillo', '.txt'].includes(extension)
      ? 'cabrillo'
      : null
  return format !== null && acceptedFormats.value.includes(format)
})
const loading = ref(true)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
const result = ref<LogSubmissionResult | null>(null)
const submissionKey = ref('')
const router = useRouter()
const route = useRoute()
const guestEmail = ref('')
const guestEmailAccess = ref(false)
const guestEmailResults = ref(false)
const guestEmailBusy = ref(false)
const guestEmailError = ref('')
const guestEmailMessage = ref('')
const emailPromptDismissed = ref(false)
const verificationResendBusy = ref(false)

const allMessages = (messages: ImportMessage[]) => messages

watch(contestSlug, () => {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
  result.value = null
  resetGuestEmailPrompt()
  submissionKey.value = ''
  progress.value = 0
})

async function loadContests() {
  error.value = ''
  loading.value = true
  try {
    contests.value = await listSubmittableContests()
    const requestedContest = route.query.contest
    if (
      typeof requestedContest === 'string' &&
      contests.value.some((item) => item.slug === requestedContest)
    ) {
      contestSlug.value = requestedContest
    }
  } catch (reason) {
    error.value =
      reason instanceof ApiError
        ? reason.message
        : 'Contest list could not be loaded.'
  } finally {
    loading.value = false
  }
}

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
  result.value = null
  resetGuestEmailPrompt()
  submissionKey.value = ''
  progress.value = 0
}

function resetGuestEmailPrompt() {
  guestEmail.value = ''
  guestEmailAccess.value = false
  guestEmailResults.value = false
  guestEmailBusy.value = false
  guestEmailError.value = ''
  guestEmailMessage.value = ''
  emailPromptDismissed.value = false
}

async function saveGuestEmail() {
  if (!result.value?.entry_id || !result.value.receipt_token || guestEmailBusy.value)
    return
  guestEmailBusy.value = true
  guestEmailError.value = ''
  guestEmailMessage.value = ''
  try {
    const response = await setGuestEntryEmail(
      result.value.entry_id,
      {
        email: guestEmail.value,
        entry_access: guestEmailAccess.value,
        result_notifications: guestEmailResults.value,
      },
      result.value.receipt_token,
    )
    guestEmailMessage.value = response.verification_email_sent
      ? 'A verification link was sent. Your email choices take effect only after you verify the address.'
      : 'Your choices are saved, but the verification email could not be sent. Use the resend option after email delivery is available.'
    emailPromptDismissed.value = true
  } catch (reason) {
    guestEmailError.value =
      reason instanceof ApiError ? reason.message : 'The email preferences could not be saved.'
  } finally {
    guestEmailBusy.value = false
  }
}

async function resendHeaderVerification() {
  if (!result.value?.entry_id || !result.value.receipt_token || verificationResendBusy.value)
    return
  verificationResendBusy.value = true
  guestEmailError.value = ''
  try {
    const response = await resendGuestEntryEmailVerification(
      result.value.entry_id,
      result.value.receipt_token,
    )
    guestEmailMessage.value = response.verification_email_sent
      ? 'A new verification link was sent to the Cabrillo EMAIL address.'
      : 'The verification email could not be sent. Try again after email delivery is available.'
  } catch (reason) {
    guestEmailError.value =
      reason instanceof ApiError ? reason.message : 'The verification email could not be resent.'
  } finally {
    verificationResendBusy.value = false
  }
}

async function submit() {
  if (
    !file.value ||
    !selectedFileAllowed.value ||
    !contestSlug.value ||
    uploading.value
  )
    return
  if (!submissionKey.value) submissionKey.value = newIdempotencyKey()
  error.value = ''
  result.value = null
  progress.value = 0
  uploading.value = true
  try {
    const response = await uploadContestLog(
      contestSlug.value,
      file.value,
      submissionKey.value,
      (percent) => {
        progress.value = percent
      },
    )
    result.value = response
  } catch (reason) {
    error.value =
      reason instanceof ApiError
        ? reason.message
        : 'The log could not be uploaded.'
  } finally {
    uploading.value = false
  }
}

function manageCreatedEntry() {
  if (!result.value?.entry_id || !result.value.receipt_token) return
  try {
    sessionStorage.setItem(
      `contestmaster-entry-${result.value.entry_id}`,
      result.value.receipt_token,
    )
  } catch {
    error.value =
      'This browser could not keep the token for navigation. Copy it before continuing.'
    return
  }
  void router.push(`/entries/${result.value.entry_id}/manage`)
}

onMounted(loadContests)
</script>

<template>
  <section class="form-card upload-card" aria-labelledby="upload-title">
    <p class="eyebrow">{{ $tr('Contest entry') }}</p>
    <h1 id="upload-title">{{ $tr('Submit a log') }}</h1>
    <p>
      {{
        $tr(
          'Choose an open contest and upload a log in one of its accepted formats. You do not need a system account.',
        )
      }}
    </p>

    <p v-if="loading" role="status">{{ $tr('Loading contests…') }}</p>
    <p v-else-if="error && !contests.length" class="form-error" role="alert">
      {{ $tr(error) }}
    </p>
    <p v-else-if="!contests.length" class="empty-state">
      {{ $tr('There are no contests accepting logs right now.') }}
    </p>

    <form v-else @submit.prevent="submit">
      <label for="upload-contest">{{ $tr('Contest') }}</label>
      <select
        id="upload-contest"
        v-model="contestSlug"
        required
        :disabled="uploading"
      >
        <option value="" disabled>{{ $tr('Select a contest') }}</option>
        <option
          v-for="contest in contests"
          :key="contest.id"
          :value="contest.slug"
        >
          {{ contest.name }}
        </option>
      </select>

      <label for="log-file">{{ fileLabel }}</label>
      <input
        id="log-file"
        ref="fileInput"
        type="file"
        :accept="fileAccept"
        required
        :disabled="uploading || acceptedFormats.length === 0"
        @change="chooseFile"
      />
      <p class="field-hint">
        <template v-if="acceptedFormats.length">
          {{
            $tr('UTF-8 text, up to 5 MiB. Accepted formats for this contest:')
          }}
          {{
            acceptedFormats.map((format) => format.toUpperCase()).join(' and ')
          }}.
        </template>
        <template v-else>
          {{ $tr('Select a contest with a configured supported log format.') }}
        </template>
        {{
          $tr(
            'ADIF records need UTC date/time, callsign, mode, band or frequency, and the exchange required by the contest.',
          )
        }}
      </p>
      <p v-if="file && !selectedFileAllowed" class="form-error" role="alert">
        {{ $tr('This file format is not enabled for the selected contest.') }}
      </p>

      <div
        v-if="uploading"
        class="upload-progress"
        role="status"
        aria-live="polite"
      >
        <label for="upload-progress"
          >{{ $tr('Upload progress:') }} {{ progress }}%</label
        >
        <progress id="upload-progress" :value="progress" max="100">
          {{ progress }}%
        </progress>
      </div>

      <p v-if="error" class="form-error" role="alert">{{ $tr(error) }}</p>
      <button
        class="primary-button"
        type="submit"
        :disabled="uploading || !file || !selectedFileAllowed || !contestSlug"
      >
        {{
          uploading
            ? 'Uploading…'
            : submissionKey
              ? 'Retry upload'
              : 'Submit log'
        }}
      </button>
    </form>

    <section
      v-if="result"
      class="import-result"
      aria-live="polite"
      aria-labelledby="result-title"
    >
      <h2 id="result-title">
        {{
          result.status === 'accepted' ? 'Log received' : 'Log needs correction'
        }}
      </h2>
      <p>
        {{ result.summary.accepted_qsos }} {{ $tr('contacts accepted;') }}
        {{ result.summary.rejected_qsos }} {{ $tr('rejected;') }}
        {{ result.summary.warning_count }} {{ $tr('warnings.') }}
      </p>
      <p v-if="result.replayed">
        {{
          $tr(
            'This retry matched an earlier submission and did not create another entry.',
          )
        }}
      </p>
      <div v-if="result.receipt_token" class="receipt-token">
        <h3>{{ $tr('Save your entry receipt token') }}</h3>
        <p>
          {{
            $tr(
              'This token gives access to this entry only. It is shown once; save it somewhere private.',
            )
          }}
        </p>
        <code>{{ result.receipt_token }}</code>
        <button
          class="secondary-button"
          type="button"
          @click="manageCreatedEntry"
        >
          {{ $tr('Manage this entry in this tab') }}
        </button>
      </div>
      <section
        v-if="result.status === 'accepted' && result.guest_email_prompt_required && result.entry_id && result.receipt_token && !result.replayed && !emailPromptDismissed"
        class="guest-email-prompt"
        aria-labelledby="guest-email-title"
      >
        <h3 id="guest-email-title">{{ $tr('Optional email choices') }}</h3>
        <p>{{ $tr('You do not need an email address or account to submit this log. If you provide an email, verify it before it can be used.') }}</p>
        <label for="guest-contact-email">{{ $tr('Email address') }}</label>
        <input id="guest-contact-email" v-model.trim="guestEmail" type="email" maxlength="320" autocomplete="email" />
        <label class="checkbox-row" for="guest-entry-access">
          <input id="guest-entry-access" v-model="guestEmailAccess" type="checkbox" />
          {{ $tr('I want to verify this address so I can amend or withdraw this entry.') }}
        </label>
        <label class="checkbox-row" for="guest-results-notices">
          <input id="guest-results-notices" v-model="guestEmailResults" type="checkbox" />
          {{ $tr('I want an email when public results are published.') }}
        </label>
        <p class="field-hint">{{ $tr('These are separate choices. Result notices are sent only after a public result list is published and contain a link to the public standings.') }}</p>
        <div class="actions">
          <button class="primary-button" type="button" :disabled="guestEmailBusy || !guestEmail || (!guestEmailAccess && !guestEmailResults)" @click="saveGuestEmail">
            {{ guestEmailBusy ? $tr('Saving…') : $tr('Save email choices') }}
          </button>
          <button class="secondary-button" type="button" :disabled="guestEmailBusy" @click="emailPromptDismissed = true">
            {{ $tr('No thanks') }}
          </button>
        </div>
      </section>
      <section
        v-if="result.status === 'accepted' && !result.guest_email_prompt_required && result.guest_email_verification_sent === true"
        class="guest-email-prompt"
        aria-labelledby="cabrillo-email-title"
      >
        <h3 id="cabrillo-email-title">{{ $tr('Verify your Cabrillo email') }}</h3>
        <p>{{ $tr('We sent a one-time verification link to the EMAIL address in your Cabrillo file. Verification enables entry access only. Result notices are not enabled by this field.') }}</p>
      </section>
      <section
        v-else-if="result.status === 'accepted' && !result.guest_email_prompt_required && result.guest_email_verification_sent === false && result.entry_id && result.receipt_token"
        class="guest-email-prompt"
        aria-labelledby="cabrillo-email-retry-title"
      >
        <h3 id="cabrillo-email-retry-title">{{ $tr('Cabrillo email verification not sent') }}</h3>
        <p>{{ $tr('The log was accepted. The verification email could not be delivered. You can retry sending it.') }}</p>
        <button class="secondary-button" type="button" :disabled="verificationResendBusy" @click="resendHeaderVerification">
          {{ verificationResendBusy ? $tr('Sending…') : $tr('Resend verification email') }}
        </button>
      </section>
      <p v-if="guestEmailMessage" role="status">{{ $tr(guestEmailMessage) }}</p>
      <p v-if="guestEmailError" class="form-error" role="alert">{{ $tr(guestEmailError) }}</p>
      <ul
        v-if="allMessages(result.errors).length"
        class="import-messages errors"
      >
        <li
          v-for="(item, index) in result.errors"
          :key="`${item.line}-${item.code}-${index}`"
        >
          <strong>{{ item.line ? `Line ${item.line}: ` : '' }}</strong
          >{{ $tr(item.message) }}
        </li>
      </ul>
      <ul
        v-if="allMessages(result.warnings).length"
        class="import-messages warnings"
      >
        <li
          v-for="(item, index) in result.warnings"
          :key="`${item.line}-${item.code}-${index}`"
        >
          <strong>{{ item.line ? `Line ${item.line}: ` : '' }}</strong
          >{{ $tr(item.message) }}
        </li>
      </ul>
    </section>
  </section>
</template>
