<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import {
  generateResults,
  getManagerResultReview,
  publishResults,
  recordQsoReview,
  updateEntryStatus,
  type ResultReview,
} from '../api/results'

const props = defineProps<{ contestId: string }>()
const router = useRouter()
const review = ref<ResultReview | null>(null)
const selectedRunIds = ref<number[]>([])
const loading = ref(true)
const busy = ref(false)
const generating = ref(false)
const error = ref('')
const message = ref('')
const reviewChoices = ref<
  Record<number, 'credited' | 'not_credited' | 'needs_review'>
>({})
const reviewReasons = ref<Record<number, string>>({})
const contestId = computed(() => Number(props.contestId))
const canPublish = computed(
  () =>
    review.value?.status === 'closed' || review.value?.status === 'published',
)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    review.value = await getManagerResultReview(contestId.value)
    selectedRunIds.value = review.value.items
      .filter((item) => item.included_by_default)
      .map((item) => item.score_run_id)
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Contest result review could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function generate() {
  if (busy.value) return
  busy.value = true
  generating.value = true
  error.value = ''
  message.value = ''
  try {
    const generated = await generateResults(contestId.value)
    generating.value = false
    message.value = `Generated ${generated.score_runs.length} score runs. ${generated.unresolved_count} item(s) need review.`
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof ApiError ? cause.message : 'Result generation failed.'
  } finally {
    generating.value = false
    busy.value = false
  }
}

async function publish() {
  if (busy.value || selectedRunIds.value.length === 0) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    const publication = await publishResults(
      contestId.value,
      selectedRunIds.value,
    )
    message.value = `Publication ${publication.publication_number} is live with ${publication.entry_count} entries.`
    await refresh()
    await router
      .replace(
        `/contests/${encodeURIComponent(review.value?.contest_slug ?? '')}/results`,
      )
      .catch(() => undefined)
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'Results could not be published.'
  } finally {
    busy.value = false
  }
}

async function decideQso(qsoId: number) {
  const reason = reviewReasons.value[qsoId]?.trim()
  if (!reason || busy.value) return
  busy.value = true
  error.value = ''
  try {
    await recordQsoReview(contestId.value, qsoId, {
      status: reviewChoices.value[qsoId] ?? 'not_credited',
      reason,
    })
    message.value = `Recorded review decision for contact ${qsoId}.`
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The review decision could not be saved.'
  } finally {
    busy.value = false
  }
}

async function setEntryStatus(
  entryId: number,
  status: 'accepted' | 'checklog' | 'withdrawn' | 'disqualified',
) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await updateEntryStatus(contestId.value, entryId, status)
    message.value = `Updated entry ${entryId} to ${status.replaceAll('_', ' ')}.`
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause.message
        : 'The entry status could not be saved.'
  } finally {
    busy.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <section class="manager-results" aria-labelledby="manager-results-title">
    <RouterLink to="/manage/contests">← Back to contests</RouterLink>
    <p class="eyebrow">Contest staff</p>
    <h1 id="manager-results-title">Generate and publish results</h1>
    <p v-if="loading" role="status" class="notice">Loading result review…</p>
    <p v-if="error" role="alert" class="error-panel">{{ error }}</p>
    <p v-if="message" role="status" class="success-panel">{{ message }}</p>
    <template v-if="review && !loading">
      <p>
        Contest status: <strong>{{ review.status }}</strong>
      </p>
      <div class="action-row">
        <button
          class="primary-button"
          type="button"
          :disabled="busy || review.status === 'draft'"
          @click="generate"
        >
          {{ busy ? 'Working…' : 'Run / rerun result generation' }}
        </button>
        <button
          class="secondary-button"
          type="button"
          :disabled="busy || !canPublish || selectedRunIds.length === 0"
          @click="publish"
        >
          Publish selected score runs
        </button>
      </div>
      <div v-if="generating" class="generation-progress">
        <progress aria-label="Calculating contest results"></progress>
        <p role="status" class="notice">
          Calculating contest results. This may take a while; keep this page open.
        </p>
      </div>

      <section class="panel" aria-labelledby="review-title">
        <h2 id="review-title">
          Unresolved items ({{ review.unresolved_count }})
        </h2>
        <p v-if="review.unresolved.length === 0" class="notice">
          No unresolved scoring items.
        </p>
        <ul v-else class="unresolved-list">
          <li
            v-for="(item, index) in review.unresolved"
            :key="`${item.entry_id}-${item.status}-${index}`"
          >
            <span
              >Entry {{ item.entry_id }} ·
              {{ String(item.status).replaceAll('_', ' ') }}</span
            >
            <span
              v-if="
                Array.isArray(item.reason_codes) && item.reason_codes.length
              "
            >
              — {{ item.reason_codes.join(', ') }}
            </span>
            <div
              v-if="item.status === 'qso_review' && Array.isArray(item.qso_ids)"
              class="qso-review-list"
            >
              <form
                v-for="qsoId in item.qso_ids"
                :key="Number(qsoId)"
                class="qso-review"
                @submit.prevent="decideQso(Number(qsoId))"
              >
                <strong>Contact {{ qsoId }}</strong>
                <label :for="`decision-${qsoId}`">Decision</label>
                <select
                  :id="`decision-${qsoId}`"
                  v-model="reviewChoices[Number(qsoId)]"
                >
                  <option value="not_credited">Not credited</option>
                  <option value="credited">Credited</option>
                  <option value="needs_review">Keep under review</option>
                </select>
                <label :for="`reason-${qsoId}`">Reason</label>
                <input
                  :id="`reason-${qsoId}`"
                  v-model="reviewReasons[Number(qsoId)]"
                  required
                  maxlength="4000"
                />
                <button class="secondary-button" type="submit" :disabled="busy">
                  Save decision
                </button>
              </form>
            </div>
            <label
              v-if="
                ['late', 'checklog', 'missing_log', 'not_scored'].includes(
                  String(item.status),
                )
              "
              class="entry-review"
            >
              Entry disposition
              <select
                :value="item.status === 'checklog' ? 'checklog' : 'accepted'"
                :disabled="busy"
                @change="
                  setEntryStatus(
                    Number(item.entry_id),
                    ($event.target as HTMLSelectElement).value as
                      'accepted' | 'checklog' | 'withdrawn' | 'disqualified',
                  )
                "
              >
                <option value="accepted">Accept</option>
                <option value="checklog">Checklog</option>
                <option value="withdrawn">Withdraw</option>
                <option value="disqualified">Disqualify</option>
              </select>
            </label>
          </li>
        </ul>
      </section>

      <section class="panel" aria-labelledby="selection-title">
        <h2 id="selection-title">Result list selection</h2>
        <p>
          Select completed runs to include in the next immutable publication.
          Withdrawn entries are excluded. Entries withheld by the ruleset policy
          cannot be selected.
        </p>
        <p v-if="review.items.length === 0" class="notice">
          Generate score runs before selecting a result list.
        </p>
        <div
          v-for="item in review.items"
          :key="item.entry_id"
          class="result-choice"
        >
          <label>
            <input
              v-model="selectedRunIds"
              type="checkbox"
              :value="item.score_run_id"
              :disabled="
                !item.included_by_default ||
                item.score_run_status !== 'completed'
              "
            />
            <span
              >{{ item.callsign }} ·
              {{ item.result_status.replaceAll('_', ' ') }} · score
              {{ item.score }}</span
            >
          </label>
          <span v-if="!item.included_by_default" class="field-help"
            >Withheld by publication policy</span
          >
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.manager-results {
  display: grid;
  gap: 1rem;
}
.panel {
  padding: 1.25rem;
  border: 1px solid var(--color-border);
  border-radius: 0.7rem;
  background: var(--color-surface);
}
.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.generation-progress {
  display: grid;
  gap: 0.35rem;
}
.generation-progress progress {
  width: 100%;
  min-height: 0.8rem;
  accent-color: var(--color-primary, #8f3427);
}
.generation-progress p {
  margin: 0;
}
.unresolved-list {
  display: grid;
  gap: 0.5rem;
  padding-left: 1.25rem;
}
.result-choice {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.7rem 0;
  border-bottom: 1px solid var(--color-border);
}
.result-choice label {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.result-choice input {
  width: 1.1rem;
  height: 1.1rem;
}
.qso-review-list {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
}
.qso-review {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: var(--color-surface-muted);
  border-radius: 0.5rem;
}
.qso-review input {
  min-width: 12rem;
  min-height: 2.25rem;
}
.qso-review select,
.entry-review select {
  min-height: 2.25rem;
}
.entry-review {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.65rem;
}
</style>
