<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import {
  createContest,
  getContest,
  previewContestSchedule,
  updateContest,
  type Contest,
  type ContestDraft,
  type ContestPeriodicity,
} from '../api/contests'
import { getCurrentUser } from '../api/identity'

const props = defineProps<{ contestId?: string }>()
interface ContestForm {
  name: string
  slug: string
  description: string
  starts_at: string
  ends_at: string
  periodicity_frequency: 'fixed' | ContestPeriodicity['frequency']
  periodicity_month: number
  periodicity_day: number
  periodicity_weekday: number
  periodicity_occurrence: number
  log_submission_cutoff_at: string
  auto_recalculate_on_upload: boolean
}

function emptyForm(): ContestForm {
  return {
    name: '',
    slug: '',
    description: '',
    starts_at: '',
    ends_at: '',
    periodicity_frequency: 'fixed',
    periodicity_month: 1,
    periodicity_day: 1,
    periodicity_weekday: 5,
    periodicity_occurrence: 1,
    log_submission_cutoff_at: '',
    auto_recalculate_on_upload: false,
  }
}

const form = reactive<ContestForm>(emptyForm())
const loading = ref(true)
const saving = ref(false)
const forbidden = ref(false)
const errorMessage = ref('')
const statusMessage = ref('')
const previewYear = ref(new Date().getUTCFullYear())
const schedulePreview = ref('')
const schedulePreviewError = ref('')
const editingId = computed(() => {
  if (props.contestId === undefined) return null
  const id = Number(props.contestId)
  return Number.isSafeInteger(id) && id > 0 ? id : NaN
})
const pageTitle = computed(() =>
  editingId.value === null ? 'Create a contest' : 'Edit contest',
)

function utcInputValue(instant: string): string {
  const date = new Date(instant)
  if (Number.isNaN(date.valueOf())) return ''
  return date.toISOString().slice(0, 16)
}

function contestForm(contest: Contest): ContestForm {
  return {
    name: contest.name,
    slug: contest.slug,
    description: contest.description ?? '',
    starts_at: utcInputValue(contest.starts_at),
    ends_at: utcInputValue(contest.ends_at),
    periodicity_frequency: contest.periodicity?.frequency ?? 'fixed',
    periodicity_month: contest.periodicity?.month ?? 1,
    periodicity_day: contest.periodicity?.day ?? 1,
    periodicity_weekday: contest.periodicity?.weekday ?? 5,
    periodicity_occurrence: contest.periodicity?.occurrence ?? 1,
    log_submission_cutoff_at: utcInputValue(contest.log_submission_cutoff_at),
    auto_recalculate_on_upload: contest.auto_recalculate_on_upload,
  }
}

function toUtcInstant(value: string): string {
  return `${value}:00Z`
}

function configuredPeriodicity(source: ContestForm): ContestPeriodicity | null {
  if (source.periodicity_frequency === 'fixed') return null
  if (source.periodicity_frequency === 'annual_date') {
    return {
      frequency: source.periodicity_frequency,
      month: source.periodicity_month,
      day: source.periodicity_day,
    }
  }
  if (source.periodicity_frequency === 'nth_weekday') {
    return {
      frequency: source.periodicity_frequency,
      month: source.periodicity_month,
      weekday: source.periodicity_weekday,
      occurrence: source.periodicity_occurrence,
    }
  }
  return { frequency: 'first_full_weekend', month: source.periodicity_month }
}

function toDraft(source: ContestForm): ContestDraft {
  return {
    name: source.name.trim(),
    slug: source.slug.trim(),
    description: source.description.trim() || null,
    starts_at: toUtcInstant(source.starts_at),
    ends_at: toUtcInstant(source.ends_at),
    periodicity: configuredPeriodicity(source),
    log_submission_cutoff_at: toUtcInstant(source.log_submission_cutoff_at),
    auto_recalculate_on_upload: source.auto_recalculate_on_upload,
  }
}

async function loadSchedulePreview() {
  schedulePreview.value = ''
  schedulePreviewError.value = ''
  const periodicity = configuredPeriodicity(form)
  if (!periodicity) return
  try {
    const preview = await previewContestSchedule(
      periodicity,
      previewYear.value,
      toUtcInstant(form.starts_at),
      toUtcInstant(form.ends_at),
    )
    schedulePreview.value = `${preview.starts_at} – ${preview.ends_at}`
  } catch (error) {
    schedulePreviewError.value =
      error instanceof Error
        ? error.message
        : 'Schedule could not be previewed.'
  }
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    await getCurrentUser()
    if (Number.isNaN(editingId.value)) {
      throw new Error('The contest identifier is invalid.')
    }
    if (editingId.value !== null) {
      const contest = await getContest(editingId.value)
      Object.assign(form, contestForm(contest))
    }
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 401) {
      forbidden.value = true
    } else {
      errorMessage.value =
        error instanceof Error
          ? error.message
          : 'Contest details could not be loaded.'
    }
  } finally {
    loading.value = false
  }
}

async function save() {
  if (saving.value) return
  saving.value = true
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    const draft = toDraft(form)
    if (editingId.value === null) {
      const contest = await createContest(draft)
      statusMessage.value = `Contest ${contest.name} created as a draft.`
      Object.assign(form, emptyForm())
    } else {
      await updateContest(editingId.value, draft)
      statusMessage.value = 'Contest details saved.'
    }
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : 'Contest details could not be saved.'
  } finally {
    saving.value = false
  }
}

watch(() => props.contestId, load, { immediate: true })
</script>

<template>
  <section class="editor-page" aria-labelledby="contest-editor-title">
    <RouterLink class="back-link" to="/manage/contests">
      ← Back to contests
    </RouterLink>
    <p class="eyebrow">Contest staff</p>
    <h1 id="contest-editor-title">{{ pageTitle }}</h1>
    <p v-if="loading" role="status" class="notice">Loading contest…</p>
    <section
      v-else-if="forbidden"
      class="panel"
      aria-labelledby="sign-in-required"
    >
      <h2 id="sign-in-required">Sign-in required</h2>
      <p>
        Sign in with a contest-manager or global-administrator account to manage
        contests.
      </p>
      <RouterLink
        class="primary-button"
        to="/sign-in?next=/manage/contests/new"
      >
        Sign in
      </RouterLink>
    </section>
    <template v-else>
      <p v-if="errorMessage" role="alert" class="error-panel">
        {{ errorMessage }}
      </p>
      <p v-if="statusMessage" role="status" class="success-panel">
        {{ statusMessage }}
      </p>
      <form class="panel contest-form" @submit.prevent="save">
        <div class="form-grid">
          <label>
            Contest name
            <input
              v-model="form.name"
              required
              maxlength="200"
              autocomplete="off"
            />
          </label>
          <label>
            URL slug
            <input
              v-model="form.slug"
              required
              maxlength="120"
              pattern="[A-Za-z0-9][A-Za-z0-9-]*"
              autocomplete="off"
              aria-describedby="slug-help"
            />
            <span id="slug-help" class="field-help"
              >Letters, numbers, and hyphens.</span
            >
          </label>
          <label class="full-width">
            Contest description (Markdown)
            <textarea
              v-model="form.description"
              maxlength="10000"
              rows="6"
              aria-describedby="contest-description-help"
            />
            <span id="contest-description-help" class="field-help"
              >Supports Markdown such as paragraphs, lists, emphasis, and links.
              This description is shown to participants above the generated
              rules summary.</span
            >
          </label>
          <label
            >Contest starts (UTC)<input
              v-model="form.starts_at"
              required
              type="datetime-local"
          /></label>
          <label
            >Contest ends (UTC)<input
              v-model="form.ends_at"
              required
              type="datetime-local"
          /></label>
          <fieldset class="full-width schedule-controls">
            <legend>Contest periodicity</legend>
            <p>
              Start, end, and recurrence belong to this contest. Times are UTC;
              the recurrence selector chooses the UTC calendar date for future
              editions. The dates above are this edition's actual instants.
            </p>
            <label
              >Schedule type
              <select v-model="form.periodicity_frequency">
                <option value="fixed">One-time contest</option>
                <option value="annual_date">Annual date</option>
                <option value="nth_weekday">Nth weekday</option>
                <option value="first_full_weekend">First full weekend</option>
              </select>
            </label>
            <label v-if="form.periodicity_frequency !== 'fixed'"
              >UTC month
              <select v-model.number="form.periodicity_month">
                <option v-for="month in 12" :key="month" :value="month">
                  {{
                    new Date(Date.UTC(2020, month - 1, 1)).toLocaleString(
                      'en',
                      { month: 'long', timeZone: 'UTC' },
                    )
                  }}
                </option>
              </select>
            </label>
            <label v-if="form.periodicity_frequency === 'annual_date'"
              >UTC day of month<input
                v-model.number="form.periodicity_day"
                type="number"
                min="1"
                max="31"
            /></label>
            <template v-if="form.periodicity_frequency === 'nth_weekday'">
              <label
                >Weekday<select v-model.number="form.periodicity_weekday">
                  <option
                    v-for="(weekday, index) in [
                      'Monday',
                      'Tuesday',
                      'Wednesday',
                      'Thursday',
                      'Friday',
                      'Saturday',
                      'Sunday',
                    ]"
                    :key="weekday"
                    :value="index"
                  >
                    {{ weekday }}
                  </option>
                </select></label
              >
              <label
                >Occurrence<select v-model.number="form.periodicity_occurrence">
                  <option :value="1">First</option>
                  <option :value="2">Second</option>
                  <option :value="3">Third</option>
                  <option :value="4">Fourth</option>
                  <option :value="5">Fifth</option>
                  <option :value="-1">Last</option>
                </select></label
              >
            </template>
            <template v-if="form.periodicity_frequency !== 'fixed'">
              <label
                >Preview year<input
                  v-model.number="previewYear"
                  type="number"
                  min="1900"
                  max="2200"
              /></label>
              <button
                type="button"
                class="secondary-button"
                @click="loadSchedulePreview"
              >
                Preview UTC dates
              </button>
              <p v-if="schedulePreview" role="status">{{ schedulePreview }}</p>
              <p v-if="schedulePreviewError" role="alert">
                {{ schedulePreviewError }}
              </p>
            </template>
          </fieldset>
          <label
            >Log submission cutoff (UTC)<input
              v-model="form.log_submission_cutoff_at"
              required
              type="datetime-local"
          /></label>
        </div>
        <label class="checkbox-field"
          ><input v-model="form.auto_recalculate_on_upload" type="checkbox" />
          Recalculate results after an accepted log upload</label
        >
        <p class="field-help">
          These values are entered and stored as UTC instants. The submission
          cutoff is independent of contest end. Category and exchange setup is
          part of the selected ruleset.
        </p>
        <button class="primary-button" type="submit" :disabled="saving">
          {{
            saving
              ? 'Saving…'
              : editingId === null
                ? 'Create draft contest'
                : 'Save contest'
          }}
        </button>
      </form>
    </template>
  </section>
</template>

<style scoped>
.editor-page {
  display: grid;
  gap: 1rem;
}
.panel {
  padding: clamp(1rem, 3vw, 1.5rem);
  border: 1px solid var(--color-border);
  border-radius: 0.8rem;
  background: var(--color-surface);
  box-shadow: 0 10px 28px var(--color-card-shadow);
}
.contest-form,
.form-grid {
  display: grid;
  gap: 0.85rem;
}
.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.form-grid label,
.schedule-controls label {
  display: grid;
  gap: 0.35rem;
  font-weight: 650;
}
.form-grid input,
.form-grid textarea,
.form-grid select {
  width: 100%;
  min-height: 2.65rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  font: inherit;
}
.full-width {
  grid-column: 1 / -1;
}
.schedule-controls {
  display: grid;
  gap: 0.8rem;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  padding: 1rem;
}
.schedule-controls legend {
  padding: 0 0.35rem;
  font-weight: 700;
}
.checkbox-field {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: fit-content;
  font-weight: 650;
}
.checkbox-field input {
  width: 1.2rem;
  height: 1.2rem;
}
.field-help {
  margin: 0;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.primary-button,
.secondary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 2.6rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-brand-700);
  background: var(--color-surface);
  font: inherit;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}
.primary-button {
  border-color: transparent;
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.primary-button:disabled {
  opacity: 0.6;
  cursor: wait;
}
.notice,
.success-panel,
.error-panel {
  padding: 0.75rem;
  border-radius: 0.45rem;
}
.notice {
  background: var(--color-surface-muted);
}
.success-panel {
  color: var(--color-success-ink);
  background: var(--color-success-surface);
}
.error-panel {
  color: var(--color-error-ink);
  background: var(--color-error-surface);
}
@media (max-width: 700px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
