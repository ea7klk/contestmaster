<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
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
const file = ref<File | null>(null)
const loading = ref(true)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
const result = ref<LogSubmissionResult | null>(null)
const submissionKey = ref('')
const router = useRouter()

const allMessages = (messages: ImportMessage[]) => messages

async function loadContests() {
  error.value = ''
  loading.value = true
  try {
    contests.value = await listSubmittableContests()
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
  if (!file.value || !contestSlug.value || uploading.value) return
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
      Choose an open contest and upload a Cabrillo log. You do not need a system
      account.
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

      <label for="log-file">Cabrillo file</label>
      <input
        id="log-file"
        type="file"
        accept=".log,.cbr,.cabrillo,.txt,text/plain"
        required
        :disabled="uploading"
        @change="chooseFile"
      />
      <p class="field-hint">
        UTF-8 text, up to 5 MiB. Include CALLSIGN, CONTEST, EMAIL (optional),
        and QSO records.
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
        :disabled="uploading || !file || !contestSlug"
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
