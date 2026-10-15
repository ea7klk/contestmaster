<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
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

function displayDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—'
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
  if (
    !globalThis.confirm(
      `Delete unreferenced ${version.dataset_key} version ${version.id}?`,
    )
  )
    return
  const reason = globalThis.prompt('Optional audit reason for this deletion:')
  if (reason === null) return
  busyVersionId.value = version.id
  error.value = ''
  statusMessage.value = ''
  try {
    await deleteMasterDataVersion(version.id, reason.trim() || undefined)
    await refresh()
    statusMessage.value = `Deleted ${version.dataset_key} version ${version.id}.`
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The version could not be deleted.'
  } finally {
    busyVersionId.value = null
  }
}

onMounted(refresh)
</script>

<template>
  <section class="master-data-page" aria-labelledby="master-data-heading">
    <h1 id="master-data-heading">Master data versions</h1>
    <p v-if="denied" role="alert">Global administrator access is required.</p>
    <p v-if="error" role="alert" class="master-data-error">{{ error }}</p>
    <p v-if="statusMessage" role="status">{{ statusMessage }}</p>
    <p v-if="loading" role="status">Loading master data history…</p>
    <template
      v-else-if="!denied && currentUser?.role === 'global_administrator'"
    >
      <div class="master-data-heading-row">
        <h2>Dataset versions</h2>
        <button type="button" class="master-data-secondary" @click="refresh">
          Refresh
        </button>
      </div>
      <p v-if="versions.length === 0">No master data versions are available.</p>
      <div v-else class="master-data-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Dataset/version</th>
              <th>State/effective interval</th>
              <th>Source provenance</th>
              <th>References</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="version in versions" :key="version.id">
              <td>
                <strong>{{ version.dataset_key }}</strong>
                <div>Version {{ version.id }} · {{ version.status }}</div>
                <div v-if="version.is_current">Current</div>
              </td>
              <td>
                <div>
                  {{ displayDate(version.valid_from) }} →
                  {{ displayDate(version.valid_to) }}
                </div>
                <div>Activated: {{ displayDate(version.activated_at) }}</div>
              </td>
              <td>
                <div>
                  {{ version.provenance.source_name }} ·
                  {{ version.provenance.status }}
                </div>
                <div>
                  Release: {{ version.provenance.source_release ?? '—' }}
                </div>
                <div>
                  Checksum:
                  <code>{{ version.provenance.checksum ?? '—' }}</code>
                </div>
                <a
                  v-if="version.provenance.source_url"
                  :href="version.provenance.source_url"
                  target="_blank"
                  rel="noreferrer"
                  >Source</a
                >
              </td>
              <td>
                <div>Contests: {{ version.references.contest }}</div>
                <div>Score runs: {{ version.references.score_run }}</div>
                <div>
                  QSO resolutions: {{ version.references.qso_resolution }}
                </div>
              </td>
              <td class="master-data-actions">
                <button
                  v-if="version.can_activate"
                  type="button"
                  :disabled="busyVersionId !== null"
                  @click="activate(version)"
                >
                  Activate
                </button>
                <button
                  v-if="version.can_delete"
                  type="button"
                  class="master-data-danger"
                  :disabled="busyVersionId !== null"
                  @click="remove(version)"
                >
                  Delete
                </button>
                <span v-if="!version.can_activate && !version.can_delete"
                  >No actions</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>Recent sync runs</h2>
      <p v-if="runs.length === 0">No sync runs have been recorded.</p>
      <div v-else class="master-data-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Dataset/source</th>
              <th>Started/finished</th>
              <th>Outcome</th>
              <th>Details</th>
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
                  No content change
                </div>
                <div v-else-if="run.change_detected === true">
                  Content changed
                </div>
                <div v-else>Change status unknown</div>
              </td>
              <td>
                <div>Records: {{ JSON.stringify(run.record_counts) }}</div>
                <div v-if="run.error_summary" class="master-data-error">
                  {{ run.error_summary }}
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
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
  border: 1px solid #dbe3e8;
  border-radius: 0.6rem;
  background: white;
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 900px;
}
th,
td {
  padding: 0.7rem;
  border-bottom: 1px solid #e3e9ed;
  text-align: left;
  vertical-align: top;
}
th {
  background: #f4f7f9;
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
  border: 1px solid #8195a2;
  border-radius: 0.35rem;
  background: white;
}
.master-data-danger {
  margin-left: 0.35rem;
  color: #8d2424;
}
.master-data-error {
  color: #8d2424;
}
</style>
