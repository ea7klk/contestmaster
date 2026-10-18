<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import ConfirmationModal from '../components/ConfirmationModal.vue'
import KeyboardScrollRegion from '../components/KeyboardScrollRegion.vue'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
import { formatUtcDateTime } from '../i18n'
import {
  activateMasterDataVersion,
  deleteMasterDataVersion,
  listMasterDataSyncRuns,
  listMasterDataVersions,
  type MasterDataSyncRun,
  type MasterDataVersion,
} from '../api/masterDataAdmin'

const currentUser = ref<PrivilegedUser | null>(null)
const versions = ref<MasterDataVersion[]>([])
const runs = ref<MasterDataSyncRun[]>([])
const loading = ref(true)
const busyVersionId = ref<number | null>(null)
const error = ref('')
const statusMessage = ref('')
const denied = ref(false)
const pendingDelete = ref<MasterDataVersion | null>(null)

function displayDate(value: string | null): string {
  return value ? formatUtcDateTime(value) : '—'
}

async function refresh() {
  loading.value = true
  error.value = ''
  statusMessage.value = ''
  try {
    const user = await getCurrentUser()
    currentUser.value = user
    if (user.role !== 'global_administrator') {
      denied.value = true
      return
    }
    const [versionResponse, runResponse] = await Promise.all([
      listMasterDataVersions(),
      listMasterDataSyncRuns(),
    ])
    versions.value = versionResponse.items
    runs.value = runResponse.items
  } catch (cause) {
    denied.value =
      cause instanceof ApiError && [401, 403].includes(cause.statusCode ?? 0)
    if (!denied.value) {
      error.value =
        cause instanceof ApiError
          ? cause.message
          : 'Master data could not be loaded.'
    }
  } finally {
    loading.value = false
  }
}

async function activate(version: MasterDataVersion) {
  if (
    !globalThis.confirm(
      `Activate ${version.dataset_key} version ${version.id}?`,
    )
  )
    return
  const reason = globalThis.prompt('Optional audit reason for this activation:')
  if (reason === null) return
  busyVersionId.value = version.id
  error.value = ''
  statusMessage.value = ''
  try {
    await activateMasterDataVersion(version.id, reason.trim() || undefined)
    await refresh()
    statusMessage.value = `Activated ${version.dataset_key} version ${version.id}.`
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The version could not be activated.'
  } finally {
    busyVersionId.value = null
  }
}

async function remove(version: MasterDataVersion) {
  pendingDelete.value = version
}

async function confirmDelete(value: { auditReason: string }) {
  const version = pendingDelete.value
  if (!version) return
  busyVersionId.value = version.id
  error.value = ''
  statusMessage.value = ''
  try {
    await deleteMasterDataVersion(version.id, value.auditReason || undefined)
    await refresh()
    statusMessage.value = `Deleted ${version.dataset_key} version ${version.id}.`
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The version could not be deleted.'
  } finally {
    busyVersionId.value = null
    pendingDelete.value = null
  }
}

onMounted(refresh)
</script>

<template>
  <section class="master-data-page" aria-labelledby="master-data-heading">
    <h1 id="master-data-heading">{{ $tr('Master data versions') }}</h1>
    <p v-if="denied" role="alert">
      {{ $tr('Global administrator access is required.') }}
    </p>
    <p v-if="error" role="alert" class="master-data-error">{{ $tr(error) }}</p>
    <p v-if="statusMessage" role="status">{{ $tr(statusMessage) }}</p>
    <p v-if="loading" role="status">
      {{ $tr('Loading master data history…') }}
    </p>
    <template
      v-else-if="!denied && currentUser?.role === 'global_administrator'"
    >
      <div class="master-data-heading-row">
        <h2>{{ $tr('Dataset versions') }}</h2>
        <button type="button" class="master-data-secondary" @click="refresh">
          {{ $tr('Refresh') }}
        </button>
      </div>
      <p v-if="versions.length === 0">
        {{ $tr('No master data versions are available.') }}
      </p>
      <KeyboardScrollRegion
        v-else
        class="master-data-table-wrap"
        label="Master data versions table"
      >
        <table>
          <thead>
            <tr>
              <th>{{ $tr('Dataset/version') }}</th>
              <th>{{ $tr('State/effective interval') }}</th>
              <th>{{ $tr('Source provenance') }}</th>
              <th>{{ $tr('References') }}</th>
              <th>{{ $tr('Actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="version in versions" :key="version.id">
              <td>
                <strong>{{ version.dataset_key }}</strong>
                <div>
                  {{ $tr('Version') }} {{ version.id }} · {{ version.status }}
                </div>
                <div v-if="version.is_current">{{ $tr('Current') }}</div>
              </td>
              <td>
                <div>
                  {{ displayDate(version.valid_from) }} →
                  {{ displayDate(version.valid_to) }}
                </div>
                <div>
                  {{ $tr('Activated:') }}
                  {{ displayDate(version.activated_at) }}
                </div>
              </td>
              <td>
                <div>
                  {{ version.provenance.source_name }} ·
                  {{ version.provenance.status }}
                </div>
                <div>
                  {{ $tr('Release:') }}
                  {{ version.provenance.source_release ?? '—' }}
                </div>
                <div>
                  {{ $tr('Checksum:') }}
                  <code>{{ version.provenance.checksum ?? '—' }}</code>
                </div>
                <a
                  v-if="version.provenance.source_url"
                  :href="version.provenance.source_url"
                  target="_blank"
                  rel="noreferrer"
                  >{{ $tr('Source') }}</a
                >
              </td>
              <td>
                <div>
                  {{ $tr('Contests:') }} {{ version.references.contest }}
                </div>
                <div>
                  {{ $tr('Score runs:') }} {{ version.references.score_run }}
                </div>
                <div>
                  {{ $tr('QSO resolutions:') }}
                  {{ version.references.qso_resolution }}
                </div>
              </td>
              <td class="master-data-actions">
                <button
                  v-if="version.can_activate"
                  type="button"
                  :disabled="busyVersionId !== null"
                  @click="activate(version)"
                >
                  {{ $tr('Activate') }}
                </button>
                <button
                  v-if="version.can_delete"
                  type="button"
                  class="master-data-danger"
                  :disabled="busyVersionId !== null"
                  @click="remove(version)"
                >
                  {{ $tr('Delete') }}
                </button>
                <span v-if="!version.can_activate && !version.can_delete">{{
                  $tr('No actions')
                }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </KeyboardScrollRegion>

      <h2>{{ $tr('Recent sync runs') }}</h2>
      <p v-if="runs.length === 0">
        {{ $tr('No sync runs have been recorded.') }}
      </p>
      <KeyboardScrollRegion
        v-else
        class="master-data-table-wrap"
        label="Master data sync history table"
      >
        <table>
          <thead>
            <tr>
              <th>{{ $tr('Dataset/source') }}</th>
              <th>{{ $tr('Started/finished') }}</th>
              <th>{{ $tr('Outcome') }}</th>
              <th>{{ $tr('Details') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id">
              <td>
                {{ run.dataset_key }}
                <div>{{ run.source_name }}</div>
              </td>
              <td>
                {{ displayDate(run.started_at) }}
                <div>{{ displayDate(run.finished_at) }}</div>
              </td>
              <td>
                {{ run.status }}
                <div v-if="run.change_detected === false">
                  {{ $tr('No content change') }}
                </div>
                <div v-else-if="run.change_detected === true">
                  {{ $tr('Content changed') }}
                </div>
                <div v-else>{{ $tr('Change status unknown') }}</div>
              </td>
              <td>
                <div>
                  {{ $tr('Records:') }} {{ JSON.stringify(run.record_counts) }}
                </div>
                <div v-if="run.error_summary" class="master-data-error">
                  {{ run.error_summary }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </KeyboardScrollRegion>
    </template>
    <ConfirmationModal
      :open="pendingDelete !== null"
      :title="
        $tr('Delete {name}?', {
          name: pendingDelete
            ? `${pendingDelete.dataset_key} version ${pendingDelete.id}`
            : '',
        })
      "
      :description="
        $tr(
          'Only unreferenced master-data versions can be deleted. This action cannot be undone.',
        )
      "
      :confirm-label="$tr('Delete')"
      :audit-reason-label="$tr('Audit reason (optional)')"
      :busy="busyVersionId !== null"
      @confirm="confirmDelete"
      @cancel="pendingDelete = null"
    />
  </section>
</template>

<style scoped>
.master-data-page {
  display: grid;
  gap: 1rem;
}
.master-data-heading-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.master-data-heading-row h2 {
  margin: 0;
}
.master-data-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface);
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 900px;
}
th,
td {
  padding: 0.7rem;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}
th {
  background: var(--color-surface-muted);
}
td div {
  margin-top: 0.25rem;
}
code {
  overflow-wrap: anywhere;
}
.master-data-actions {
  white-space: nowrap;
}
button {
  cursor: pointer;
  padding: 0.45rem 0.65rem;
}
.master-data-secondary {
  border: 1px solid var(--color-border-strong);
  border-radius: 0.35rem;
  background: var(--color-surface);
}
.master-data-danger {
  margin-left: 0.35rem;
  color: var(--color-error-ink);
}
.master-data-error {
  color: var(--color-error-ink);
}
</style>
