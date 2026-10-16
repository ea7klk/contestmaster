<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ApiError } from '../api/client'
import KeyboardScrollRegion from '../components/KeyboardScrollRegion.vue'
import { getPublicResults, type PublicResultsPage } from '../api/results'
import { formatInteger, formatUtcDateTime } from '../i18n'

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
  () =>
    result.value?.filters.categories.find((item) => item.key === category.value)
      ?.values ?? [],
)
const exportBase = computed(
  () =>
    `${import.meta.env.VITE_API_PREFIX ?? '/api/v1'}/public/contests/${encodeURIComponent(props.slug)}/results/export`,
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
      cause instanceof ApiError
        ? cause.message
        : 'Contest results could not be loaded.'
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
  () => [
    props.slug,
    page.value,
    category.value,
    value.value,
    band.value,
    mode.value,
    status.value,
  ],
  loadResults,
  { immediate: true },
)
</script>

<template>
  <section class="results-page" aria-labelledby="results-title">
    <p class="eyebrow">{{ $tr('Published contest results') }}</p>
    <h1 id="results-title">{{ result?.contest.name ?? 'Contest results' }}</h1>
    <p v-if="result" class="results-publication">
      {{ $tr('Publication') }} {{ result.contest.publication.number }} ·
      {{ formatUtcDateTime(result.contest.publication.published_at) }}
    </p>
    <p v-if="result?.contest.description" class="intro">
      {{ result.contest.description }}
    </p>
    <p
      v-if="result?.contest.publication.withheld_count"
      class="notice"
      role="status"
    >
      {{ result.contest.publication.withheld_count }} {{ $tr('entr')
      }}{{
        result.contest.publication.withheld_count === 1 ? 'y was' : 'ies were'
      }}
      {{ $tr('withheld from this publication.') }}
    </p>
    <nav
      v-if="result"
      :aria-label="$tr('Download published results')"
      class="export-links"
    >
      <a :href="`${exportBase}?format=json`" download>{{
        $tr('Download JSON v1')
      }}</a>
      <a :href="`${exportBase}?format=csv`" download>{{
        $tr('Download CSV v1')
      }}</a>
    </nav>

    <p v-if="loading" role="status" class="notice">
      {{ $tr('Loading results…') }}
    </p>
    <p v-else-if="error" role="alert" class="error-panel">{{ $tr(error) }}</p>
    <template v-else-if="result">
      <form
        class="result-filters panel"
        :aria-label="$tr('Filter results')"
        @submit.prevent
      >
        <label v-if="result.filters.categories.length">
          {{ $tr('Category dimension') }}
          <select
            :value="category"
            @change="changeCategory(($event.target as HTMLSelectElement).value)"
          >
            <option value="">{{ $tr('All categories') }}</option>
            <option
              v-for="item in result.filters.categories"
              :key="item.key"
              :value="item.key"
            >
              {{ item.key }}
            </option>
          </select>
        </label>
        <label v-if="category">
          {{ $tr('Category value') }}
          <select v-model="value" :disabled="categoryValues.length === 0">
            <option value="">{{ $tr('All values') }}</option>
            <option v-for="item in categoryValues" :key="item" :value="item">
              {{ item }}
            </option>
          </select>
        </label>
        <label v-if="result.filters.bands.length">
          {{ $tr('Band') }}
          <select v-model="band">
            <option value="">{{ $tr('All bands') }}</option>
            <option
              v-for="item in result.filters.bands"
              :key="item"
              :value="item"
            >
              {{ item }}
            </option>
          </select>
        </label>
        <label v-if="result.filters.modes.length">
          {{ $tr('Mode') }}
          <select v-model="mode">
            <option value="">{{ $tr('All modes') }}</option>
            <option
              v-for="item in result.filters.modes"
              :key="item"
              :value="item"
            >
              {{ item }}
            </option>
          </select>
        </label>
        <label>
          {{ $tr('Result status') }}
          <select v-model="status">
            <option value="">{{ $tr('All published statuses') }}</option>
            <option
              v-for="item in result.filters.statuses"
              :key="item"
              :value="item"
            >
              {{ item.replaceAll('_', ' ') }}
            </option>
          </select>
        </label>
        <button class="quiet-button" type="button" @click="resetFilters">
          {{ $tr('Clear filters') }}
        </button>
      </form>

      <p class="result-count" aria-live="polite">
        {{ $tr('Showing') }} {{ result.items.length }} {{ $tr('of') }}
        {{ formatInteger(result.meta.total) }} {{ $tr('published entries.') }}
      </p>
      <KeyboardScrollRegion
        v-if="result.items.length"
        class="results-table-wrap"
        label="Published standings table"
      >
        <table class="results-table">
          <caption class="visually-hidden">
            {{
              $tr('Published contest standings')
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">{{ $tr('Place') }}</th>
              <th scope="col">{{ $tr('Callsign') }}</th>
              <th scope="col">{{ $tr('Categories') }}</th>
              <th scope="col">{{ $tr('Credited QSOs') }}</th>
              <th scope="col">{{ $tr('Score') }}</th>
              <th scope="col">{{ $tr('Status') }}</th>
              <th scope="col">{{ $tr('Explanation') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in result.items" :key="item.id">
              <td>{{ item.placement ?? '—' }}</td>
              <th scope="row">{{ item.callsign }}</th>
              <td>
                {{
                  Object.entries(item.category_values)
                    .map(([key, entry]) => `${key}: ${entry}`)
                    .join(', ') || '—'
                }}
              </td>
              <td>
                {{ formatInteger(item.credited_qso_count) }} /
                {{ formatInteger(item.qso_count) }}
              </td>
              <td>{{ formatInteger(item.score) }}</td>
              <td>
                <span class="result-status">{{
                  item.status.replaceAll('_', ' ')
                }}</span>
              </td>
              <td>
                <details>
                  <summary>{{ $tr('Score details') }}</summary>
                  <dl class="score-explanation">
                    <div>
                      <dt>{{ $tr('QSO points') }}</dt>
                      <dd>{{ formatInteger(item.explanation.points) }}</dd>
                    </div>
                    <div>
                      <dt>{{ $tr('Multipliers') }}</dt>
                      <dd>{{ formatInteger(item.explanation.multipliers) }}</dd>
                    </div>
                    <div>
                      <dt>{{ $tr('Bonuses') }}</dt>
                      <dd>
                        {{ formatInteger(item.explanation.bonus_points) }}
                      </dd>
                    </div>
                    <div>
                      <dt>{{ $tr('Penalties') }}</dt>
                      <dd>
                        {{ formatInteger(item.explanation.penalty_points) }}
                      </dd>
                    </div>
                    <div>
                      <dt>{{ $tr('Final score') }}</dt>
                      <dd>{{ formatInteger(item.explanation.score) }}</dd>
                    </div>
                  </dl>
                  <p>{{ item.explanation.summary }}</p>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </KeyboardScrollRegion>
      <p v-else class="notice">
        {{ $tr('No published entries match these filters.') }}
      </p>
      <nav class="pagination" :aria-label="$tr('Results pages')">
        <button
          class="secondary-button"
          type="button"
          :disabled="page <= 1"
          @click="page--"
        >
          {{ $tr('Previous page') }}
        </button>
        <span
          >{{ $tr('Page') }} {{ result.meta.page }} {{ $tr('of') }}
          {{ Math.max(result.meta.pages, 1) }}</span
        >
        <button
          class="secondary-button"
          type="button"
          :disabled="page >= result.meta.pages"
          @click="page++"
        >
          {{ $tr('Next page') }}
        </button>
      </nav>
    </template>
  </section>
</template>

<style scoped>
.results-page {
  display: grid;
  gap: 1rem;
}
.results-publication,
.result-count {
  color: var(--color-muted);
}
.export-links,
.pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 1rem;
}
.result-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.85rem;
}
.result-filters label {
  display: grid;
  flex: 1 1 12rem;
  gap: 0.35rem;
  font-weight: 650;
}
.result-filters select {
  width: 100%;
  min-width: 9rem;
  min-height: 2.5rem;
  padding: 0.4rem;
}
.panel {
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.65rem;
  background: var(--color-surface);
}
.results-table-wrap {
  overflow-x: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 0.65rem;
}
.results-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}
.results-table th,
.results-table td {
  padding: 0.75rem;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: top;
}
.results-table thead {
  background: var(--color-surface-muted);
}
.results-table th {
  font-weight: 700;
}
.result-status {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 1rem;
  background: var(--color-surface-muted);
  text-transform: capitalize;
}
.score-explanation {
  display: grid;
  gap: 0.25rem;
}
.score-explanation div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.score-explanation dt {
  font-weight: 600;
}
.score-explanation dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.pagination {
  justify-content: space-between;
}
@media (max-width: 640px) {
  .pagination {
    justify-content: center;
  }
}
</style>
