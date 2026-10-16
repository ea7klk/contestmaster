<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import {
  listSubmittableContests,
  newIdempotencyKey,
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

const allMessages = (messages: ImportMessage[]) => messages

watch(contestSlug, () => {
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
  result.value = null
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
  submissionKey.value = ''
  progress.value = 0
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
    <p class="eyebrow">Contest entry</p>
    <h1 id="upload-title">Submit a log</h1>
    <p>
      Choose an open contest and upload a log in one of its accepted formats.
      You do not need a system account.
    </p>

    <p v-if="loading" role="status">Loading contests…</p>
    <p v-else-if="error && !contests.length" class="form-error" role="alert">
      {{ error }}
    </p>
    <p v-else-if="!contests.length" class="empty-state">
      There are no contests accepting logs right now.
    </p>

    <form v-else @submit.prevent="submit">
      <label for="upload-contest">Contest</label>
      <select
        id="upload-contest"
        v-model="contestSlug"
        required
        :disabled="uploading"
      >
        <option value="" disabled>Select a contest</option>
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
          UTF-8 text, up to 5 MiB. Accepted formats for this contest:
          {{
            acceptedFormats.map((format) => format.toUpperCase()).join(' and ')
          }}.
        </template>
        <template v-else>
          Select a contest with a configured supported log format.
        </template>
        ADIF records need UTC date/time, callsign, mode, band or frequency, and
        the exchange required by the contest.
      </p>
      <p v-if="file && !selectedFileAllowed" class="form-error" role="alert">
        This file format is not enabled for the selected contest.
      </p>

      <div
        v-if="uploading"
        class="upload-progress"
        role="status"
        aria-live="polite"
      >
        <label for="upload-progress">Upload progress: {{ progress }}%</label>
        <progress id="upload-progress" :value="progress" max="100">
          {{ progress }}%
        </progress>
      </div>

      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
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
        {{ result.summary.accepted_qsos }} contacts accepted;
        {{ result.summary.rejected_qsos }} rejected;
        {{ result.summary.warning_count }} warnings.
      </p>
      <p v-if="result.replayed">
        This retry matched an earlier submission and did not create another
        entry.
      </p>
      <div v-if="result.receipt_token" class="receipt-token">
        <h3>Save your entry receipt token</h3>
        <p>
          This token gives access to this entry only. It is shown once; save it
          somewhere private.
        </p>
        <code>{{ result.receipt_token }}</code>
        <button
          class="secondary-button"
          type="button"
          @click="manageCreatedEntry"
        >
          Manage this entry in this tab
        </button>
      </div>
      <ul
        v-if="allMessages(result.errors).length"
        class="import-messages errors"
      >
        <li
          v-for="(item, index) in result.errors"
          :key="`${item.line}-${item.code}-${index}`"
        >
          <strong>{{ item.line ? `Line ${item.line}: ` : '' }}</strong
          >{{ item.message }}
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
          >{{ item.message }}
        </li>
      </ul>
    </section>
  </section>
</template>
