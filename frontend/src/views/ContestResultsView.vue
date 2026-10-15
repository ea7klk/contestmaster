<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/client'
import { getPublicResults, type PublicResultsPage } from '../api/results'

const props = defineProps<{ slug: string }>()
const result = ref<PublicResultsPage | null>(null)
const loading = ref(true)
const error = ref('')
const page = ref(1)
const category = ref('')
const value = ref('')
const band = ref('')
const mode = ref('')
const status = ref('')
let activeRequest: AbortController | undefined

const categoryValues = computed(
  () => result.value?.filters.categories.find((item) => item.key === category.value)?.values ?? [],
)
const exportBase = computed(
  () => `${import.meta.env.VITE_API_PREFIX ?? '/api/v1'}/public/contests/${encodeURIComponent(props.slug)}/results/export`,
)

async function loadResults() {
  activeRequest?.abort()
  const controller = new AbortController()
  activeRequest = controller
  loading.value = true
  error.value = ''
  try {
    result.value = await getPublicResults(
      props.slug,
      {
        page: page.value,
        category: category.value,
        value: value.value,
        band: band.value,
        mode: mode.value,
        status: status.value,
      },
      controller.signal,
    )
  } catch (cause) {
    if (controller.signal.aborted) return
    error.value =
      cause instanceof ApiError ? cause.message : 'Contest results could not be loaded.'
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}

function resetFilters() {
  category.value = ''
  value.value = ''
  band.value = ''
  mode.value = ''
  status.value = ''
  page.value = 1
}

function changeCategory(next: string) {
  category.value = next
  value.value = ''
  page.value = 1
}

watch(
  () => [props.slug, page.value, category.value, value.value, band.value, mode.value, status.value],
  loadResults,
  { immediate: true },
)
</script>

<template>
  <section class="results-page" aria-labelledby="results-title">
    <p class="eyebrow">Published contest results</p>
    <h1 id="results-title">{{ result?.contest.name ?? 'Contest results' }}</h1>
    <p v-if="result" class="results-publication">
      Publication {{ result.contest.publication.number }} ·
      {{ new Date(result.contest.publication.published_at).toLocaleString() }}
    </p>
    <p v-if="result?.contest.description" class="intro">
      {{ result.contest.description }}
    </p>
    <p v-if="result?.contest.publication.withheld_count" class="notice" role="status">
      {{ result.contest.publication.withheld_count }} entr{{
        result.contest.publication.withheld_count === 1 ? 'y was' : 'ies were'
      }} withheld from this publication.
    </p>
    <nav v-if="result" aria-label="Download published results" class="export-links">
      <a :href="`${exportBase}?format=json`" download>Download JSON v1</a>
      <a :href="`${exportBase}?format=csv`" download>Download CSV v1</a>
    </nav>

    <p v-if="loading" role="status" class="notice">Loading results…</p>
    <p v-else-if="error" role="alert" class="error-panel">{{ error }}</p>
    <template v-else-if="result">
      <form class="result-filters panel" aria-label="Filter results" @submit.prevent>
        <label v-if="result.filters.categories.length">
          Category dimension
          <select :value="category" @change="changeCategory(($event.target as HTMLSelectElement).value)">
            <option value="">All categories</option>
            <option v-for="item in result.filters.categories" :key="item.key" :value="item.key">
              {{ item.key }}
            </option>
          </select>
        </label>
        <label v-if="category">
          Category value
          <select v-model="value" :disabled="categoryValues.length === 0">
            <option value="">All values</option>
            <option v-for="item in categoryValues" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <label v-if="result.filters.bands.length">
          Band
          <select v-model="band">
            <option value="">All bands</option>
            <option v-for="item in result.filters.bands" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <label v-if="result.filters.modes.length">
          Mode
          <select v-model="mode">
            <option value="">All modes</option>
            <option v-for="item in result.filters.modes" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <label>
          Result status
          <select v-model="status">
            <option value="">All published statuses</option>
            <option v-for="item in result.filters.statuses" :key="item" :value="item">
              {{ item.replaceAll('_', ' ') }}
            </option>
          </select>
        </label>
        <button class="quiet-button" type="button" @click="resetFilters">Clear filters</button>
      </form>

      <p class="result-count" aria-live="polite">
        Showing {{ result.items.length }} of {{ result.meta.total }} published entries.
      </p>
      <div v-if="result.items.length" class="results-table-wrap">
        <table class="results-table">
          <caption class="visually-hidden">Published contest standings</caption>
          <thead>
            <tr>
              <th scope="col">Place</th>
              <th scope="col">Callsign</th>
              <th scope="col">Categories</th>
              <th scope="col">Credited QSOs</th>
              <th scope="col">Score</th>
              <th scope="col">Status</th>
              <th scope="col">Explanation</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in result.items" :key="item.id">
              <td>{{ item.placement ?? '—' }}</td>
              <th scope="row">{{ item.callsign }}</th>
              <td>{{ Object.entries(item.category_values).map(([key, entry]) => `${key}: ${entry}`).join(', ') || '—' }}</td>
              <td>{{ item.credited_qso_count }} / {{ item.qso_count }}</td>
              <td>{{ item.score }}</td>
              <td><span class="result-status">{{ item.status.replaceAll('_', ' ') }}</span></td>
              <td>
                <details>
                  <summary>Score details</summary>
                  <dl class="score-explanation">
                    <div><dt>QSO points</dt><dd>{{ item.explanation.points }}</dd></div>
                    <div><dt>Multipliers</dt><dd>{{ item.explanation.multipliers }}</dd></div>
                    <div><dt>Bonuses</dt><dd>{{ item.explanation.bonus_points }}</dd></div>
                    <div><dt>Penalties</dt><dd>{{ item.explanation.penalty_points }}</dd></div>
                    <div><dt>Final score</dt><dd>{{ item.explanation.score }}</dd></div>
                  </dl>
                  <p>{{ item.explanation.summary }}</p>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="notice">No published entries match these filters.</p>
      <nav class="pagination" aria-label="Results pages">
        <button class="secondary-button" type="button" :disabled="page <= 1" @click="page--">
          Previous page
        </button>
        <span>Page {{ result.meta.page }} of {{ Math.max(result.meta.pages, 1) }}</span>
        <button class="secondary-button" type="button" :disabled="page >= result.meta.pages" @click="page++">
          Next page
        </button>
      </nav>
    </template>
  </section>
</template>

<style scoped>
.results-page { display: grid; gap: 1rem; }
.results-publication, .result-count { color: #536a78; }
.export-links, .pagination { display: flex; flex-wrap: wrap; align-items: center; gap: 1rem; }
.result-filters { display: flex; flex-wrap: wrap; align-items: end; gap: 0.85rem; }
.result-filters label { display: grid; gap: 0.35rem; font-weight: 650; }
.result-filters select { min-width: 9rem; min-height: 2.5rem; padding: 0.4rem; }
.panel { padding: 1rem; border: 1px solid #d4e0e5; border-radius: 0.65rem; background: white; }
.results-table-wrap { overflow-x: auto; background: white; border: 1px solid #d4e0e5; border-radius: 0.65rem; }
.results-table { width: 100%; border-collapse: collapse; min-width: 760px; }
.results-table th, .results-table td { padding: 0.75rem; border-bottom: 1px solid #e2e9ed; text-align: left; vertical-align: top; }
.results-table thead { background: #f2f6f8; }
.results-table th { font-weight: 700; }
.result-status { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 1rem; background: #edf3f5; text-transform: capitalize; }
.score-explanation { display: grid; gap: 0.25rem; }
.score-explanation div { display: flex; justify-content: space-between; gap: 1rem; }
.score-explanation dt { font-weight: 600; }
.score-explanation dd { margin: 0; font-variant-numeric: tabular-nums; }
.pagination { justify-content: space-between; }
@media (max-width: 640px) { .pagination { justify-content: center; } }
</style>
