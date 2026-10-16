<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError } from '../api/client'
import KeyboardScrollRegion from '../components/KeyboardScrollRegion.vue'
import {
  addEntryContact,
  downloadEntryRevision,
  editEntryContact,
  getManagedEntry,
  newIdempotencyKey,
  removeEntryContact,
  resubmitEntryLog,
  type ContactWrite,
  type ManagedEntry,
} from '../api/logs'
import { formatInteger, formatUtcDateTime } from '../i18n'

const route = useRoute()
const entryId = Number(route.params.entryId)
const receiptToken = ref('')
const entry = ref<ManagedEntry | null>(null)
const acceptedFormats = computed(() => entry.value?.accepted_formats ?? [])
const revisionAccept = computed(() =>
  acceptedFormats.value
    .flatMap((format) =>
      format === 'cabrillo'
        ? ['.log', '.cbr', '.cabrillo', '.txt']
        : format === 'adif'
          ? ['.adi', '.adif']
          : [],
    )
    .join(','),
)
const revisionFileLabel = computed(() => {
  if (
    acceptedFormats.value.includes('adif') &&
    acceptedFormats.value.includes('cabrillo')
  ) {
    return 'Corrected log file (Cabrillo or ADI/ADIF)'
  }
  if (acceptedFormats.value.includes('adif'))
    return 'Corrected log file (ADI/ADIF)'
  if (acceptedFormats.value.includes('cabrillo'))
    return 'Corrected log file (Cabrillo)'
  return 'Corrected log file'
})
const revisionFileAllowed = computed(() => {
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
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const file = ref<File | null>(null)
const uploadProgress = ref(0)
const uploadKey = ref('')
const downloading = ref(false)
const editingContactId = ref<number | null>(null)
const contact = reactive({
  occurredAt: new Date().toISOString().slice(0, 16),
  callsign: '',
  frequency: '',
  mode: '',
  exchangeSent: '',
  exchangeReceived: '',
})

function readStoredReceipt() {
  try {
    receiptToken.value =
      sessionStorage.getItem(`contestmaster-entry-${entryId}`) ?? ''
  } catch {
    receiptToken.value = ''
  }
}

async function loadEntry() {
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    entry.value = await getManagedEntry(
      entryId,
      receiptToken.value || undefined,
    )
  } catch (cause) {
    entry.value = null
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Entry could not be loaded. Check the entry ID and access token.'
  } finally {
    loading.value = false
  }
}

function resetContact() {
  editingContactId.value = null
  Object.assign(contact, {
    occurredAt: new Date().toISOString().slice(0, 16),
    callsign: '',
    frequency: '',
    mode: '',
    exchangeSent: '',
    exchangeReceived: '',
  })
}

function beginEdit(item: ManagedEntry['contacts'][number]) {
  editingContactId.value = item.id
  Object.assign(contact, {
    occurredAt: new Date(item.occurred_at).toISOString().slice(0, 16),
    callsign: item.callsign,
    frequency: item.frequency ?? '',
    mode: item.mode ?? '',
    exchangeSent: item.exchange_sent.raw ?? '',
    exchangeReceived: item.exchange_received.raw ?? '',
  })
}

function contactPayload(): ContactWrite {
  return {
    occurred_at: new Date(contact.occurredAt).toISOString(),
    callsign: contact.callsign.trim(),
    frequency: contact.frequency.trim(),
    mode: contact.mode.trim(),
    exchange_sent: contact.exchangeSent ? { raw: contact.exchangeSent } : {},
    exchange_received: contact.exchangeReceived
      ? { raw: contact.exchangeReceived }
      : {},
  }
}

async function saveContact() {
  if (!entry.value || saving.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    entry.value = editingContactId.value
      ? await editEntryContact(
          entryId,
          editingContactId.value,
          contactPayload(),
          receiptToken.value || undefined,
        )
      : await addEntryContact(
          entryId,
          contactPayload(),
          receiptToken.value || undefined,
        )
    message.value = `Revision ${entry.value.revision_number} saved.`
    resetContact()
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The contact could not be saved.'
  } finally {
    saving.value = false
  }
}

async function deleteContact(contactId: number) {
  if (!entry.value || saving.value) return
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    entry.value = await removeEntryContact(
      entryId,
      contactId,
      receiptToken.value || undefined,
    )
    message.value = `Revision ${entry.value.revision_number} saved.`
    if (editingContactId.value === contactId) resetContact()
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The contact could not be removed.'
  } finally {
    saving.value = false
  }
}

function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  uploadKey.value = ''
  uploadProgress.value = 0
}

async function resubmit() {
  if (!file.value || !revisionFileAllowed.value || saving.value) return
  if (!uploadKey.value) uploadKey.value = newIdempotencyKey()
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await resubmitEntryLog(
      entryId,
      file.value,
      uploadKey.value,
      receiptToken.value || undefined,
      (percent) => (uploadProgress.value = percent),
    )
    if (result.status === 'rejected') {
      error.value = result.errors
        .map((item) => `Line ${item.line}: ${item.message}`)
        .join(' ')
    } else {
      await loadEntry()
      message.value = result.replayed
        ? 'This retry matched the existing revision.'
        : `Revision ${result.revision_number} saved.`
    }
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The log could not be resubmitted.'
  } finally {
    saving.value = false
  }
}

async function downloadCurrentRevision() {
  if (!entry.value?.revision_id || downloading.value) return
  downloading.value = true
  error.value = ''
  try {
    const result = await downloadEntryRevision(
      entryId,
      entry.value.revision_id,
      receiptToken.value || undefined,
    )
    const url = URL.createObjectURL(result.blob)
    const link = document.createElement('a')
    link.href = url
    link.download = result.filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The submitted log could not be downloaded.'
  } finally {
    downloading.value = false
  }
}

onMounted(() => {
  readStoredReceipt()
  if (entryId > 0) void loadEntry()
  else error.value = 'Entry ID is invalid.'
})
</script>

<template>
  <section
    class="page-card upload-card"
    aria-labelledby="entry-management-title"
  >
    <p class="eyebrow">{{ $tr('Entry access') }}</p>
    <h1 id="entry-management-title">{{ $tr('Manage log entry') }}</h1>
    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <p v-if="message" role="status" aria-live="polite">{{ $tr(message) }}</p>

    <form v-if="!entry" class="stacked-form" @submit.prevent="loadEntry">
      <label for="entry-id">{{ $tr('Entry ID') }}</label>
      <input id="entry-id" :value="entryId" readonly />
      <label for="entry-receipt">{{ $tr('Entry receipt token') }}</label>
      <input
        id="entry-receipt"
        v-model.trim="receiptToken"
        autocomplete="off"
        type="password"
        required
      />
      <button class="primary-button" type="submit" :disabled="loading">
        {{ loading ? 'Loading…' : 'Open entry' }}
      </button>
    </form>

    <div v-else>
      <p>
        {{ $tr('Entry') }} {{ entry.entry_key }} {{ $tr('· revision') }}
        {{
          entry.revision_number === null
            ? '—'
            : formatInteger(entry.revision_number)
        }}
      </p>
      <button
        v-if="entry.revision_id"
        class="secondary-button"
        type="button"
        :disabled="downloading"
        @click="downloadCurrentRevision"
      >
        {{
          downloading
            ? 'Preparing download…'
            : 'Download original submitted log (source v1)'
        }}
      </button>
      <KeyboardScrollRegion
        class="table-scroll"
        label="Contacts in the current entry revision"
      >
        <table>
          <caption class="visually-hidden">
            {{
              $tr('Contacts in the current entry revision')
            }}
          </caption>
          <thead>
            <tr>
              <th>{{ $tr('UTC time') }}</th>
              <th>{{ $tr('Callsign') }}</th>
              <th>{{ $tr('Frequency') }}</th>
              <th>{{ $tr('Mode') }}</th>
              <th>{{ $tr('Actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in entry.contacts" :key="item.id">
              <td>
                {{
                  formatUtcDateTime(item.occurred_at, {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                  })
                }}
              </td>
              <td>{{ item.callsign }}</td>
              <td>{{ item.frequency }}</td>
              <td>{{ item.mode }}</td>
              <td>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="saving"
                  @click="beginEdit(item)"
                >
                  {{ $tr('Edit') }}
                </button>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="saving"
                  @click="deleteContact(item.id)"
                >
                  {{ $tr('Remove') }}
                </button>
              </td>
            </tr>
            <tr v-if="entry.contacts.length === 0">
              <td colspan="5">{{ $tr('No contacts in this revision.') }}</td>
            </tr>
          </tbody>
        </table>
      </KeyboardScrollRegion>

      <form class="stacked-form" @submit.prevent="saveContact">
        <h2>{{ editingContactId ? 'Edit contact' : 'Add contact' }}</h2>
        <label for="contact-time">{{ $tr('Contact time') }}</label>
        <input
          id="contact-time"
          v-model="contact.occurredAt"
          type="datetime-local"
          required
        />
        <label for="contact-callsign">{{ $tr('Worked callsign') }}</label>
        <input
          id="contact-callsign"
          v-model.trim="contact.callsign"
          maxlength="32"
          required
        />
        <label for="contact-frequency">{{ $tr('Frequency or band') }}</label>
        <input
          id="contact-frequency"
          v-model.trim="contact.frequency"
          maxlength="24"
          required
        />
        <label for="contact-mode">{{ $tr('Mode') }}</label>
        <input
          id="contact-mode"
          v-model.trim="contact.mode"
          maxlength="40"
          required
        />
        <label for="contact-exchange-sent">{{ $tr('Exchange sent') }}</label>
        <input id="contact-exchange-sent" v-model="contact.exchangeSent" />
        <label for="contact-exchange-received">{{
          $tr('Exchange received')
        }}</label>
        <input
          id="contact-exchange-received"
          v-model="contact.exchangeReceived"
        />
        <div class="button-row">
          <button class="primary-button" type="submit" :disabled="saving">
            {{
              saving
                ? 'Saving…'
                : editingContactId
                  ? 'Save contact'
                  : 'Add contact'
            }}
          </button>
          <button
            v-if="editingContactId"
            class="secondary-button"
            type="button"
            @click="resetContact"
          >
            {{ $tr('Cancel edit') }}
          </button>
        </div>
      </form>

      <form class="stacked-form" @submit.prevent="resubmit">
        <h2>{{ $tr('Replace log file') }}</h2>
        <label for="revision-file">{{ revisionFileLabel }}</label>
        <input
          id="revision-file"
          type="file"
          :accept="revisionAccept"
          @change="chooseFile"
        />
        <p class="field-hint">
          <template v-if="acceptedFormats.length">
            {{ $tr('This contest accepts') }}
            {{
              acceptedFormats
                .map((format) => format.toUpperCase())
                .join(' and ')
            }}{{ $tr('. Use UTF-8 text, up to 5 MiB.') }}
          </template>
          <template v-else>
            {{
              $tr(
                'This contest has no supported log format enabled in its ruleset.',
              )
            }}
          </template>
        </p>
        <p v-if="file && !revisionFileAllowed" class="form-error" role="alert">
          {{ $tr('This file format is not enabled for this contest.') }}
        </p>
        <div
          v-if="saving && file"
          class="upload-progress"
          role="status"
          aria-live="polite"
        >
          <label for="revision-progress"
            >{{ $tr('Upload progress:') }} {{ uploadProgress }}%</label
          >
          <progress id="revision-progress" :value="uploadProgress" max="100">
            {{ uploadProgress }}%
          </progress>
        </div>
        <button
          class="secondary-button"
          type="submit"
          :disabled="saving || !file || !revisionFileAllowed"
        >
          {{ saving ? 'Saving…' : 'Upload new revision' }}
        </button>
      </form>
    </div>
  </section>
</template>
