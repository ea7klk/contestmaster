<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import {
  createContest,
  importContest,
  listContests,
  selectRuleset,
  updateContest,
  type Contest,
  type ContestDraft,
  type ContestImportPackage,
} from '../api/contests'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
import { listRulesetVersions, type SavedRulesetVersion } from '../api/rulesets'

interface ContestForm {
  name: string
  slug: string
  description: string
  starts_at: string
  ends_at: string
  log_submission_cutoff_at: string
  auto_recalculate_on_upload: boolean
}

const user = ref<PrivilegedUser | null>(null)
const contests = ref<Contest[]>([])
const rulesets = ref<SavedRulesetVersion[]>([])
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const forbidden = ref(false)
const editingId = ref<number | null>(null)
const statusMessage = ref('')
const rulesetSelections = reactive<Record<number, string>>({})
const rulesetSavingId = ref<number | null>(null)
const importing = ref(false)

function emptyForm(): ContestForm {
  return {
    name: '',
    slug: '',
    description: '',
    starts_at: '',
    ends_at: '',
    log_submission_cutoff_at: '',
    auto_recalculate_on_upload: false,
  }
}

const form = reactive<ContestForm>(emptyForm())
const formTitle = computed(() =>
  editingId.value === null ? 'Create a contest' : 'Edit contest',
)

function localInputValue(instant: string): string {
  const date = new Date(instant)
  if (Number.isNaN(date.valueOf())) return ''
  const local = new Date(date.valueOf() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function toUtcInstant(value: string): string {
  return new Date(value).toISOString()
}

function contestForm(contest: Contest): ContestForm {
  return {
    name: contest.name,
    slug: contest.slug,
    description: contest.description ?? '',
    starts_at: localInputValue(contest.starts_at),
    ends_at: localInputValue(contest.ends_at),
    log_submission_cutoff_at: localInputValue(contest.log_submission_cutoff_at),
    auto_recalculate_on_upload: contest.auto_recalculate_on_upload,
  }
}

function toDraft(source: ContestForm): ContestDraft {
  return {
    name: source.name.trim(),
    slug: source.slug.trim(),
    description: source.description.trim() || null,
    starts_at: toUtcInstant(source.starts_at),
    ends_at: toUtcInstant(source.ends_at),
    log_submission_cutoff_at: toUtcInstant(source.log_submission_cutoff_at),
    auto_recalculate_on_upload: source.auto_recalculate_on_upload,
  }
}

async function refreshData() {
  loading.value = true
  errorMessage.value = ''
  forbidden.value = false
  try {
    const [currentUser, contestList, rulesetList] = await Promise.all([
      getCurrentUser(),
      listContests(),
      listRulesetVersions(),
    ])
    user.value = currentUser
    contests.value = contestList.items
    rulesets.value = rulesetList.items
    for (const contest of contestList.items) {
      if (contest.ruleset_version_id !== null) {
        rulesetSelections[contest.id] = String(contest.ruleset_version_id)
      }
    }
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 401) {
      forbidden.value = true
    } else {
      errorMessage.value =
        error instanceof ApiError
          ? error.message
          : 'Contest data could not be loaded.'
    }
  } finally {
    loading.value = false
  }
}

function editContest(contest: Contest) {
  Object.assign(form, contestForm(contest))
  editingId.value = contest.id
  statusMessage.value = ''
  errorMessage.value = ''
}

function cancelEdit() {
  Object.assign(form, emptyForm())
  editingId.value = null
  errorMessage.value = ''
  statusMessage.value = ''
}

async function saveContest() {
  if (saving.value) return
  saving.value = true
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    const draft = toDraft(form)
    const editing = editingId.value
    if (editingId.value === null) {
      await createContest(draft)
    } else {
      await updateContest(editingId.value, draft)
    }
    cancelEdit()
    await refreshData()
    statusMessage.value =
      editing === null
        ? 'Contest created as a draft.'
        : 'Contest details saved.'
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : 'Contest details could not be saved.'
  } finally {
    saving.value = false
  }
}

async function saveRuleset(contest: Contest) {
  const versionId = Number(rulesetSelections[contest.id])
  if (!Number.isInteger(versionId) || versionId <= 0) return
  rulesetSavingId.value = contest.id
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    await selectRuleset(contest.id, versionId)
    statusMessage.value = `Ruleset assigned to ${contest.name}.`
    await refreshData()
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : 'The ruleset could not be assigned.'
  } finally {
    rulesetSavingId.value = null
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function importContestFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  errorMessage.value = ''
  statusMessage.value = ''
  if (file.size > 1_000_000) {
    errorMessage.value = 'Contest import files must be smaller than 1 MB.'
    input.value = ''
    return
  }
  importing.value = true
  try {
    const parsed: unknown = JSON.parse(await file.text())
    if (
      !isRecord(parsed) ||
      !isRecord(parsed.contest) ||
      !isRecord(parsed.ruleset)
    ) {
      throw new Error(
        'Expected a contest package with contest and ruleset objects.',
      )
    }
    if (
      parsed.ruleset.schema_version !== 1 ||
      typeof parsed.ruleset.ruleset_key !== 'string' ||
      !Array.isArray(parsed.ruleset.rules)
    ) {
      throw new Error(
        'The package ruleset must be a schema-version-1 ruleset draft.',
      )
    }
    const result = await importContest(
      parsed as unknown as ContestImportPackage,
    )
    await refreshData()
    statusMessage.value = `Imported ${result.contest.name} as a draft with its ruleset assigned.`
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : error instanceof SyntaxError
          ? 'The selected file is not valid JSON.'
          : error instanceof Error
            ? error.message
            : 'The contest package could not be imported.'
  } finally {
    importing.value = false
    input.value = ''
  }
}

onMounted(refreshData)
</script>

<template>
  <section class="manager-page" aria-labelledby="manager-title">
    <div class="manager-heading">
      <div>
        <p class="eyebrow">Contest staff</p>
        <h1 id="manager-title">Contest manager</h1>
        <p v-if="user" class="intro">
          Signed in as {{ user.display_name }} ({{
            user.role.replaceAll('_', ' ')
          }}).
        </p>
      </div>
      <div class="manager-actions">
        <label class="file-button">
          {{ importing ? 'Importing…' : 'Import contest' }}
          <input
            class="visually-hidden"
            type="file"
            accept="application/json,.json"
            :disabled="importing"
            @change="importContestFile"
          />
        </label>
        <RouterLink class="secondary-button" to="/rulesets/compose">
          Create a ruleset
        </RouterLink>
      </div>
    </div>

    <p v-if="loading" role="status" class="notice">Loading your contests…</p>
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
      <RouterLink class="primary-link" to="/sign-in?next=/manage/contests">
        Sign in
      </RouterLink>
    </section>
    <p v-if="errorMessage" class="error-panel" role="alert">
      {{ errorMessage }}
    </p>
    <p v-if="statusMessage" class="success-panel" role="status">
      {{ statusMessage }}
    </p>

    <p v-if="!loading && !forbidden" class="field-help">
      Import a JSON package with contest metadata and a schema-version-1 ruleset
      draft. The imported contest starts as a draft.
    </p>

    <form
      v-if="!loading && !forbidden"
      class="panel contest-form"
      @submit.prevent="saveContest"
    >
      <div class="section-title">
        <h2>{{ formTitle }}</h2>
        <button
          v-if="editingId !== null"
          class="quiet-button"
          type="button"
          @click="cancelEdit"
        >
          Cancel edit
        </button>
      </div>
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
          Description
          <textarea v-model="form.description" maxlength="10000" rows="3" />
        </label>
        <label>
          Contest starts (your local time)
          <input v-model="form.starts_at" required type="datetime-local" />
        </label>
        <label>
          Contest ends (your local time)
          <input v-model="form.ends_at" required type="datetime-local" />
        </label>
        <label>
          Log submission cutoff (your local time)
          <input
            v-model="form.log_submission_cutoff_at"
            required
            type="datetime-local"
          />
        </label>
      </div>
      <label class="checkbox-field">
        <input v-model="form.auto_recalculate_on_upload" type="checkbox" />
        Recalculate results after an accepted log upload
      </label>
      <p class="field-help">
        Times are converted to UTC before submission. Cutoff is stored
        separately from contest end. Category and exchange setup is part of the
        selected ruleset.
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

    <section
      v-if="!loading && !forbidden"
      class="contest-list"
      aria-labelledby="contest-list-title"
    >
      <h2 id="contest-list-title">Your contests</h2>
      <p v-if="contests.length === 0" class="notice">
        You have not created a contest yet.
      </p>
      <article
        v-for="contest in contests"
        :key="contest.id"
        class="panel contest-card"
      >
        <div class="section-title">
          <div>
            <p class="eyebrow">{{ contest.status }}</p>
            <h3>{{ contest.name }}</h3>
            <p class="field-help">/{{ contest.slug }}</p>
          </div>
          <button
            class="secondary-button"
            type="button"
            @click="editContest(contest)"
          >
            Edit details
          </button>
        </div>
        <RouterLink :to="`/manage/contests/${contest.id}/results`">
          Generate and publish results
        </RouterLink>
        <dl class="contest-meta">
          <div>
            <dt>Starts</dt>
            <dd>{{ new Date(contest.starts_at).toLocaleString() }}</dd>
          </div>
          <div>
            <dt>Ends</dt>
            <dd>{{ new Date(contest.ends_at).toLocaleString() }}</dd>
          </div>
          <div>
            <dt>Log cutoff</dt>
            <dd>
              {{ new Date(contest.log_submission_cutoff_at).toLocaleString() }}
            </dd>
          </div>
          <div>
            <dt>Automatic recalculation</dt>
            <dd>{{ contest.auto_recalculate_on_upload ? 'On' : 'Off' }}</dd>
          </div>
        </dl>
        <div class="ruleset-row">
          <label :for="`ruleset-${contest.id}`">
            Ruleset and category definition
            <select
              :id="`ruleset-${contest.id}`"
              v-model="rulesetSelections[contest.id]"
              :disabled="contest.status !== 'draft' || rulesets.length === 0"
            >
              <option value="">Select a saved ruleset</option>
              <option
                v-for="version in rulesets"
                :key="version.id"
                :value="String(version.id)"
              >
                {{ version.ruleset_key }} · {{ version.version }} ({{
                  version.rule_type_keys.includes('categories')
                    ? 'categories configured'
                    : 'no categories'
                }})
              </option>
            </select>
          </label>
          <button
            class="secondary-button"
            type="button"
            :disabled="
              contest.status !== 'draft' ||
              !rulesetSelections[contest.id] ||
              rulesetSavingId === contest.id
            "
            @click="saveRuleset(contest)"
          >
            {{
              rulesetSavingId === contest.id ? 'Assigning…' : 'Assign ruleset'
            }}
          </button>
          <RouterLink
            v-if="contest.ruleset_version_id !== null"
            class="secondary-button"
            :to="`/rulesets/compose/${contest.ruleset_version_id}`"
          >
            Edit ruleset
          </RouterLink>
        </div>
        <p v-if="contest.ruleset_version_id === null" class="field-help">
          This draft needs a validated ruleset before it can be opened.
        </p>
      </article>
    </section>
  </section>
</template>

<style scoped>
.manager-page,
.contest-list {
  display: grid;
  gap: 1rem;
}
.manager-heading,
.section-title,
.ruleset-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.manager-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.file-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.75rem;
  padding: 0.6rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.55rem;
  color: var(--color-ink);
  background: var(--color-surface);
  cursor: pointer;
  font-weight: 650;
}
.file-button:focus-within {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.manager-heading h1,
.contest-card h3 {
  margin-top: 0.25rem;
}
.panel {
  padding: clamp(1rem, 3vw, 1.5rem);
  border: 1px solid var(--color-border);
  border-radius: 0.8rem;
  background: var(--color-surface);
  box-shadow: 0 10px 28px var(--color-card-shadow);
}
.contest-form,
.form-grid,
.contest-card,
.ruleset-row label {
  display: grid;
  gap: 0.85rem;
}
.form-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.form-grid label,
.ruleset-row label {
  font-weight: 650;
}
.form-grid input,
.form-grid textarea,
.ruleset-row select {
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
.contest-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.7rem 1.25rem;
  margin: 0;
}
.contest-meta div {
  min-width: 0;
}
.contest-meta dt {
  color: var(--color-muted);
  font-size: 0.85rem;
}
.contest-meta dd {
  margin: 0.15rem 0 0;
  overflow-wrap: anywhere;
}
.primary-button,
.secondary-button,
.quiet-button,
.primary-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.6rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid transparent;
  border-radius: 0.45rem;
  font: inherit;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}
.primary-button,
.primary-link {
  width: fit-content;
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.secondary-button {
  color: var(--color-brand-700);
  background: var(--color-surface);
  border-color: var(--color-border-strong);
}
.quiet-button {
  color: var(--color-brand-900);
  background: var(--color-surface-muted);
}
.primary-button:disabled,
.secondary-button:disabled {
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
  .manager-heading,
  .ruleset-row {
    align-items: stretch;
    flex-direction: column;
  }
  .form-grid,
  .contest-meta {
    grid-template-columns: 1fr;
  }
}
</style>
