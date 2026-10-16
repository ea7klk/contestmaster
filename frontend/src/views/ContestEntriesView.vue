<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { getContest, type Contest } from '../api/contests'
import {
  downloadContestLogRevision,
  getContestLogDetails,
  listContestLogs,
  type ContestLogDetails,
  type ContestLogList,
} from '../api/logs'

const route = useRoute()
const router = useRouter()
const contestId = computed(() => Number(route.params.contestId))
const entryId = computed(() => {
  const value = Number(route.params.entryId)
  return Number.isInteger(value) && value > 0 ? value : null
})
const revisionId = computed(() => {
  const value = Number(route.query.revision)
  return Number.isInteger(value) && value > 0 ? value : undefined
})
const contest = ref<Contest | null>(null)
const logList = ref<ContestLogList | null>(null)
const detail = ref<ContestLogDetails | null>(null)
const searchInput = ref('')
const appliedSearch = ref('')
const listPage = ref(1)
const detailPage = ref(1)
const loading = ref(true)
const detailLoading = ref(false)
const downloading = ref(false)
const error = ref('')
const detailError = ref('')

function messageFor(cause: unknown, fallback: string) {
  return cause instanceof ApiError ? cause.message : fallback
}

async function loadPage() {
  loading.value = true
  error.value = ''
  try {
    const [contestData, entries] = await Promise.all([
      getContest(contestId.value),
      listContestLogs(contestId.value, listPage.value, appliedSearch.value),
    ])
    contest.value = contestData
    logList.value = entries
  } catch (cause) {
    error.value = messageFor(cause, 'Submitted logs could not be loaded.')
  } finally {
    loading.value = false
  }
}

async function loadDetails() {
  if (entryId.value === null) {
    detail.value = null
    detailError.value = ''
    return
  }
  detailLoading.value = true
  detailError.value = ''
  try {
    detail.value = await getContestLogDetails(
      contestId.value,
      entryId.value,
      detailPage.value,
      revisionId.value,
    )
  } catch (cause) {
    detail.value = null
    detailError.value = messageFor(cause, 'Log details could not be loaded.')
  } finally {
    detailLoading.value = false
  }
}

function applySearch() {
  appliedSearch.value = searchInput.value.trim()
  listPage.value = 1
  void loadPage()
}

function changeListPage(nextPage: number) {
  listPage.value = nextPage
  void loadPage()
}

function changeDetailPage(nextPage: number) {
  detailPage.value = nextPage
  void loadDetails()
}

function selectRevision(event: Event) {
  const selected = Number((event.target as HTMLSelectElement).value)
  const query = { ...route.query }
  if (Number.isInteger(selected) && selected > 0) query.revision = String(selected)
  else delete query.revision
  detailPage.value = 1
  void router.replace({ query })
}

function exchangeText(values: Record<string, unknown>) {
  const parts = Object.entries(values).map(([key, value]) => `${key}: ${String(value)}`)
  return parts.join(', ') || '—'
}

async function downloadSelectedRevision() {
  if (!detail.value || downloading.value) return
  downloading.value = true
  detailError.value = ''
  try {
    const result = await downloadContestLogRevision(
      contestId.value,
      detail.value.entry.entry_id,
      detail.value.entry.revision_id ?? detail.value.revisions[0]?.id ?? 0,
    )
    const url = URL.createObjectURL(result.blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = result.filename
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (cause) {
    detailError.value = messageFor(cause, 'The original log could not be downloaded.')
  } finally {
    downloading.value = false
  }
}

onMounted(() => {
  void loadPage()
  void loadDetails()
})

watch(
  () => [route.params.entryId, route.query.revision],
  () => {
    detailPage.value = 1
    void loadDetails()
  },
)

watch(
  () => route.params.contestId,
  () => {
    listPage.value = 1
    detailPage.value = 1
    void loadPage()
    void loadDetails()
  },
)
</script>

<template>
  <section class="submitted-logs-page" aria-labelledby="submitted-logs-title">
    <p class="eyebrow">Contest staff</p>
    <h1 id="submitted-logs-title">Submitted logs</h1>
    <p v-if="contest" class="intro">{{ contest.name }}</p>
    <p v-if="error" class="error-panel" role="alert">{{ error }}</p>
    <p v-if="loading" role="status" class="notice">Loading submitted logs…</p>

    <template v-if="!loading && logList">
      <section class="panel submitted-log-list" aria-labelledby="log-list-title">
        <div class="section-title">
          <h2 id="log-list-title">Log entries ({{ logList.meta.total }})</h2>
          <RouterLink class="quiet-link" to="/manage/contests">
            Back to contests
          </RouterLink>
        </div>
        <form class="log-search" role="search" @submit.prevent="applySearch">
          <label for="log-search-input">Filter by callsign or entry key</label>
          <div class="log-search-controls">
            <input
              id="log-search-input"
              v-model="searchInput"
              type="search"
              maxlength="120"
              autocomplete="off"
            />
            <button class="secondary-button" type="submit">Search</button>
          </div>
        </form>
        <p v-if="logList.items.length === 0" class="notice">
          {{ appliedSearch ? 'No submitted logs match this filter.' : 'No logs have been submitted for this contest yet.' }}
        </p>
        <div v-else class="table-scroll" tabindex="0" aria-label="Scrollable submitted logs list">
          <table>
            <thead>
              <tr>
                <th scope="col">Callsign</th>
                <th scope="col">Status</th>
                <th scope="col">Submitted</th>
                <th scope="col">Format</th>
                <th scope="col">Revision</th>
                <th scope="col">QSOs</th>
                <th scope="col"><span class="visually-hidden">Details</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in logList.items" :key="item.entry_id">
                <th scope="row">{{ item.callsign }}</th>
                <td>{{ item.status }}{{ item.is_late ? ' · late' : '' }}</td>
                <td>{{ new Date(item.submitted_at).toLocaleString() }}</td>
                <td>{{ item.input_format ?? '—' }}</td>
                <td>{{ item.revision_number ?? '—' }}</td>
                <td>{{ item.qso_count }}</td>
                <td>
                  <RouterLink
                    :to="`/manage/contests/${contestId}/entries/${item.entry_id}`"
                    :aria-label="`View log details for ${item.callsign}`"
                  >
View log
</RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <nav v-if="logList.meta.pages > 1" class="page-controls" aria-label="Submitted logs pages">
          <button
            class="secondary-button"
            type="button"
            :disabled="listPage <= 1 || loading"
            @click="changeListPage(listPage - 1)"
          >
Previous
</button>
          <span>Page {{ logList.meta.page }} of {{ logList.meta.pages }}</span>
          <button
            class="secondary-button"
            type="button"
            :disabled="listPage >= logList.meta.pages || loading"
            @click="changeListPage(listPage + 1)"
          >
Next
</button>
        </nav>
      </section>

      <section v-if="entryId !== null" class="panel log-detail" aria-labelledby="log-detail-title">
        <p v-if="detailLoading" role="status" class="notice">Loading log details…</p>
        <p v-if="detailError" class="error-panel" role="alert">{{ detailError }}</p>
        <template v-if="detail && !detailLoading">
          <div class="section-title">
            <div>
              <p class="eyebrow">{{ detail.entry.status }}{{ detail.entry.is_late ? ' · late' : '' }}</p>
              <h2 id="log-detail-title">{{ detail.entry.callsign }}</h2>
            </div>
            <button
              class="secondary-button"
              type="button"
              :disabled="downloading"
              @click="downloadSelectedRevision"
            >
{{ downloading ? 'Preparing…' : 'Download original log' }}
</button>
          </div>
          <dl class="log-detail-meta">
            <div><dt>Entry key</dt><dd>{{ detail.entry.entry_key }}</dd></div>
            <div><dt>Submitted</dt><dd>{{ new Date(detail.entry.submitted_at).toLocaleString() }}</dd></div>
            <div><dt>Filename</dt><dd>{{ detail.entry.original_filename ?? 'Unknown filename' }}</dd></div>
            <div><dt>Category</dt><dd>{{ exchangeText(detail.entry.category_values) }}</dd></div>
          </dl>
          <label for="log-revision">Log revision</label>
          <select id="log-revision" :value="detail.entry.revision_id" @change="selectRevision">
            <option v-for="revision in detail.revisions" :key="revision.id" :value="revision.id">
              Revision {{ revision.revision_number }} · {{ revision.input_format }} · {{ revision.qso_count }} QSOs
            </option>
          </select>
          <div v-if="detail.contacts.length" class="table-scroll qso-table-scroll" tabindex="0" aria-label="Scrollable QSO details">
            <table>
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">UTC time</th>
                  <th scope="col">Worked callsign</th>
                  <th scope="col">Band / frequency</th>
                  <th scope="col">Mode</th>
                  <th scope="col">Exchange sent</th>
                  <th scope="col">Exchange received</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="contact in detail.contacts" :key="contact.id">
                  <td>{{ contact.source_line_number ?? '—' }}</td>
                  <td>{{ new Date(contact.occurred_at).toISOString().replace('T', ' ').slice(0, 19) }}</td>
                  <td>{{ contact.callsign }}</td>
                  <td>{{ contact.band ?? '—' }}</td>
                  <td>{{ contact.mode ?? '—' }}</td>
                  <td>{{ exchangeText(contact.exchange_sent) }}</td>
                  <td>{{ exchangeText(contact.exchange_received) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="notice">This revision contains no parsed QSOs.</p>
          <nav v-if="detail.meta.pages > 1" class="page-controls" aria-label="QSO detail pages">
            <button class="secondary-button" type="button" :disabled="detailPage <= 1 || detailLoading" @click="changeDetailPage(detailPage - 1)">Previous QSOs</button>
            <span>QSOs page {{ detail.meta.page }} of {{ detail.meta.pages }}</span>
            <button class="secondary-button" type="button" :disabled="detailPage >= detail.meta.pages || detailLoading" @click="changeDetailPage(detailPage + 1)">Next QSOs</button>
          </nav>
        </template>
      </section>
    </template>
  </section>
</template>

<style scoped>
.submitted-logs-page {
  display: grid;
  gap: 1rem;
}

.submitted-logs-page h1,
.submitted-logs-page h2,
.submitted-logs-page p {
  margin-top: 0;
}

.submitted-log-list,
.log-detail {
  display: grid;
  gap: 1rem;
}

.log-search-controls,
.page-controls,
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.log-search-controls input {
  flex: 1;
}

.table-scroll {
  max-width: 100%;
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 0.6rem;
  border-bottom: 1px solid var(--border-color, #d8c9c3);
  text-align: left;
  vertical-align: top;
}

th {
  white-space: nowrap;
}

.log-detail-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem 1rem;
  margin: 0;
}

.log-detail-meta dt {
  font-weight: 700;
}

.log-detail-meta dd {
  margin: 0.2rem 0 0;
  overflow-wrap: anywhere;
}

.qso-table-scroll {
  max-height: 36rem;
}

@media (max-width: 42rem) {
  .section-title,
  .page-controls {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
