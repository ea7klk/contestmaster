<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError } from '../api/client'
import {
  addEntryContact,
  editEntryContact,
  getManagedEntry,
  newIdempotencyKey,
  removeEntryContact,
  resubmitEntryLog,
  type ContactWrite,
  type ManagedEntry,
} from '../api/logs'

const route = useRoute()
const entryId = Number(route.params.entryId)
const receiptToken = ref('')
const entry = ref<ManagedEntry | null>(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const message = ref('')
const file = ref<File | null>(null)
const uploadProgress = ref(0)
const uploadKey = ref('')
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
  if (!file.value || saving.value) return
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
    <p class="eyebrow">Entry access</p>
    <h1 id="entry-management-title">Manage log entry</h1>
    <p v-if="error" role="alert" class="form-error">{{ error }}</p>
    <p v-if="message" role="status" aria-live="polite">{{ message }}</p>

    <form v-if="!entry" class="stacked-form" @submit.prevent="loadEntry">
      <label for="entry-id">Entry ID</label>
      <input id="entry-id" :value="entryId" readonly />
      <label for="entry-receipt">Entry receipt token</label>
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
      <p>Entry {{ entry.entry_key }} · revision {{ entry.revision_number }}</p>
      <div class="table-scroll">
        <table>
          <caption class="visually-hidden">
            Contacts in the current entry revision
          </caption>
          <thead>
            <tr>
              <th>UTC time</th>
              <th>Callsign</th>
              <th>Frequency</th>
              <th>Mode</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in entry.contacts" :key="item.id">
              <td>{{ new Date(item.occurred_at).toISOString() }}</td>
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
                  Edit
                </button>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="saving"
                  @click="deleteContact(item.id)"
                >
                  Remove
                </button>
              </td>
            </tr>
            <tr v-if="entry.contacts.length === 0">
              <td colspan="5">No contacts in this revision.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <form class="stacked-form" @submit.prevent="saveContact">
        <h2>{{ editingContactId ? 'Edit contact' : 'Add contact' }}</h2>
        <label for="contact-time">Contact time</label>
        <input
          id="contact-time"
          v-model="contact.occurredAt"
          type="datetime-local"
          required
        />
        <label for="contact-callsign">Worked callsign</label>
        <input
          id="contact-callsign"
          v-model.trim="contact.callsign"
          maxlength="32"
          required
        />
        <label for="contact-frequency">Frequency or band</label>
        <input
          id="contact-frequency"
          v-model.trim="contact.frequency"
          maxlength="24"
          required
        />
        <label for="contact-mode">Mode</label>
        <input
          id="contact-mode"
          v-model.trim="contact.mode"
          maxlength="40"
          required
        />
        <label for="contact-exchange-sent">Exchange sent</label>
        <input id="contact-exchange-sent" v-model="contact.exchangeSent" />
        <label for="contact-exchange-received">Exchange received</label>
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
            Cancel edit
          </button>
        </div>
      </form>

      <form class="stacked-form" @submit.prevent="resubmit">
        <h2>Replace log file</h2>
        <label for="revision-file">Corrected Cabrillo file</label>
        <input
          id="revision-file"
          type="file"
          accept=".log,.cbr,.cabrillo,.txt"
          @change="chooseFile"
        />
        <div
          v-if="saving && file"
          class="upload-progress"
          role="status"
          aria-live="polite"
        >
          <label for="revision-progress"
            >Upload progress: {{ uploadProgress }}%</label
          >
          <progress id="revision-progress" :value="uploadProgress" max="100">
            {{ uploadProgress }}%
          </progress>
        </div>
        <button
          class="secondary-button"
          type="submit"
          :disabled="saving || !file"
        >
          {{ saving ? 'Saving…' : 'Upload new revision' }}
        </button>
      </form>
    </div>
  </section>
</template>
