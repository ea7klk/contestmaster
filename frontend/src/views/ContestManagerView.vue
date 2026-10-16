<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import {
  changeContestStatus,
  deleteContest,
  importContest,
  listContests,
  selectRuleset,
  type Contest,
  type ContestImportPackage,
  type ContestStatus,
} from '../api/contests'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
import {
  listAllRulesetVersions,
  type SavedRulesetVersion,
} from '../api/rulesets'

const pageSize = 20
const user = ref<PrivilegedUser | null>(null)
const contests = ref<Contest[]>([])
const rulesets = ref<SavedRulesetVersion[]>([])
const loading = ref(true)
const forbidden = ref(false)
const errorMessage = ref('')
const statusMessage = ref('')
const contestFilter = ref('')
const page = ref(1)
const total = ref(0)
const pages = ref(0)
const rulesetSelections = reactive<Record<number, string>>({})
const rulesetSavingId = ref<number | null>(null)
const statusSavingId = ref<number | null>(null)
const importing = ref(false)
const deletingContestId = ref<number | null>(null)
const filteredContests = computed(() => contests.value)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function refreshData() {
  loading.value = true
  errorMessage.value = ''
  forbidden.value = false
  try {
    const [currentUser, contestList, allRulesets] = await Promise.all([
      getCurrentUser(),
      listContests(page.value, pageSize, contestFilter.value),
      listAllRulesetVersions(),
    ])
    user.value = currentUser
    contests.value = contestList.items
    total.value = contestList.meta.total
    pages.value = contestList.meta.pages
    rulesets.value = allRulesets
    for (const contest of contestList.items) {
      if (contest.ruleset_version_id !== null) {
        rulesetSelections[contest.id] = String(contest.ruleset_version_id)
      }
    }
  } catch (error) {
    if (error instanceof ApiError && error.statusCode === 401)
      forbidden.value = true
    else
      errorMessage.value =
        error instanceof Error
          ? error.message
          : 'Contest data could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function applyFilter() {
  page.value = 1
  await refreshData()
}

async function changePage(nextPage: number) {
  if (nextPage < 1 || nextPage > pages.value || nextPage === page.value) return
  page.value = nextPage
  await refreshData()
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
      error instanceof Error
        ? error.message
        : 'The ruleset could not be assigned.'
  } finally {
    rulesetSavingId.value = null
  }
}

async function setContestStatus(contest: Contest, status: ContestStatus) {
  statusSavingId.value = contest.id
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    await changeContestStatus(contest.id, status)
    await refreshData()
    statusMessage.value =
      status === 'open'
        ? `${contest.name} is now open to the public.`
        : `${contest.name} is now closed.`
  } catch (error) {
    errorMessage.value =
      error instanceof Error
        ? error.message
        : 'The contest status could not be changed.'
  } finally {
    statusSavingId.value = null
  }
}

async function removeContest(contest: Contest) {
  const typedSlug = globalThis.prompt(
    `Permanently delete “${contest.name}” and all of its uploaded logs, scoring, results, and contest history? This cannot be undone. Type the contest slug (${contest.slug}) to confirm.`,
  )
  if (typedSlug === null || typedSlug !== contest.slug) return
  deletingContestId.value = contest.id
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    await deleteContest(contest.id, typedSlug)
    if (contests.value.length === 1 && page.value > 1) page.value -= 1
    await refreshData()
    statusMessage.value = `${contest.name} and its contest data were deleted.`
  } catch (error) {
    errorMessage.value =
      error instanceof Error
        ? error.message
        : 'The contest could not be deleted.'
  } finally {
    deletingContestId.value = null
  }
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
      parsed.ruleset.schema_version !== 2 ||
      typeof parsed.ruleset.ruleset_key !== 'string' ||
      !Array.isArray(parsed.ruleset.rules)
    ) {
      throw new Error(
        'The package ruleset must be a schema-version-2 ruleset draft.',
      )
    }
    const result = await importContest(
      parsed as unknown as ContestImportPackage,
    )
    page.value = 1
    contestFilter.value = ''
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
        <RouterLink class="secondary-button" to="/manage/contests/new">
          Create a contest
        </RouterLink>
        <RouterLink class="secondary-button" to="/manage/rulesets">
          Manage rulesets
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
    <template v-else>
      <p v-if="errorMessage" class="error-panel" role="alert">
        {{ errorMessage }}
      </p>
      <p v-if="statusMessage" class="success-panel" role="status">
        {{ statusMessage }}
      </p>
      <p class="field-help">
        Import a JSON package with contest metadata and a schema-version-2
        ruleset draft. The imported contest starts as a draft.
      </p>
      <section class="contest-list" aria-labelledby="contest-list-title">
        <div class="contest-list-heading">
          <h2 id="contest-list-title">Your contests</h2>
          <label for="contest-filter"
            >Filter contests
            <input
              id="contest-filter"
              v-model="contestFilter"
              type="search"
              maxlength="120"
              autocomplete="off"
              placeholder="Name, slug, or status"
              aria-describedby="contest-filter-help"
              @input="applyFilter"
            />
            <span id="contest-filter-help" class="field-help"
              >Search by contest name, URL slug, or exact status.</span
            >
          </label>
        </div>
        <p v-if="total === 0 && !contestFilter" class="notice">
          You have not created a contest yet.
        </p>
        <p
          v-else-if="filteredContests.length === 0"
          class="notice"
          role="status"
        >
          No contests match “{{ contestFilter }}”.
        </p>
        <div
          v-else
          class="contest-list-scroll"
          tabindex="0"
          aria-label="Scrollable contest list"
        >
          <article
            v-for="contest in filteredContests"
            :key="contest.id"
            class="panel contest-card"
          >
            <div class="section-title">
              <div>
                <p class="eyebrow">{{ contest.status }}</p>
                <h3>{{ contest.name }}</h3>
                <p class="field-help">/{{ contest.slug }}</p>
              </div>
              <div class="contest-card-actions">
                <button
                  v-if="
                    contest.status === 'draft' &&
                    contest.ruleset_version_id !== null
                  "
                  class="primary-button"
                  type="button"
                  :disabled="statusSavingId === contest.id"
                  @click="setContestStatus(contest, 'open')"
                >
                  {{
                    statusSavingId === contest.id ? 'Opening…' : 'Open contest'
                  }}
                </button>
                <button
                  v-else-if="contest.status === 'open'"
                  class="secondary-button"
                  type="button"
                  :disabled="statusSavingId === contest.id"
                  @click="setContestStatus(contest, 'closed')"
                >
                  {{
                    statusSavingId === contest.id ? 'Closing…' : 'Close contest'
                  }}
                </button>
                <button
                  v-else-if="
                    contest.status === 'closed' &&
                    contest.ruleset_version_id !== null
                  "
                  class="primary-button"
                  type="button"
                  :disabled="statusSavingId === contest.id"
                  @click="setContestStatus(contest, 'open')"
                >
                  {{
                    statusSavingId === contest.id
                      ? 'Reopening…'
                      : 'Reopen contest'
                  }}
                </button>
                <RouterLink
                  class="secondary-button"
                  :to="`/manage/contests/${contest.id}/edit`"
                >
                  Edit details
                </RouterLink>
                <button
                  class="danger-button"
                  type="button"
                  :disabled="deletingContestId === contest.id"
                  @click="removeContest(contest)"
                >
                  {{
                    deletingContestId === contest.id
                      ? 'Deleting…'
                      : 'Delete contest'
                  }}
                </button>
              </div>
            </div>
            <p
              v-if="
                contest.status === 'draft' &&
                contest.ruleset_version_id !== null
              "
              class="field-help"
            >
              Opening makes this contest public and eligible for log
              submissions.
            </p>
            <div class="contest-links">
              <span>
                <RouterLink :to="`/manage/contests/${contest.id}/results`"
                  >Generate and publish results</RouterLink
                >
              </span>
              <span>
                <RouterLink :to="`/manage/contests/${contest.id}/entries`"
                  >Submitted logs</RouterLink
                >
              </span>
            </div>
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
                  {{
                    new Date(contest.log_submission_cutoff_at).toLocaleString()
                  }}
                </dd>
              </div>
              <div>
                <dt>Automatic recalculation</dt>
                <dd>{{ contest.auto_recalculate_on_upload ? 'On' : 'Off' }}</dd>
              </div>
            </dl>
            <div class="ruleset-row">
              <label :for="`ruleset-${contest.id}`"
                >Ruleset and category definition
                <select
                  :id="`ruleset-${contest.id}`"
                  v-model="rulesetSelections[contest.id]"
                  :disabled="
                    contest.status !== 'draft' || rulesets.length === 0
                  "
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
                  rulesetSavingId === contest.id
                    ? 'Assigning…'
                    : 'Assign ruleset'
                }}
              </button>
              <RouterLink
                v-if="contest.ruleset_version_id !== null"
                class="secondary-button"
                :to="`/manage/rulesets/${contest.ruleset_version_id}/edit`"
              >
                Edit ruleset
              </RouterLink>
            </div>
            <p v-if="contest.ruleset_version_id === null" class="field-help">
              This draft needs a validated ruleset before it can be opened.
            </p>
          </article>
        </div>
        <nav
          v-if="pages > 1"
          class="pagination"
          aria-label="Contest list pages"
        >
          <button
            class="secondary-button"
            type="button"
            :disabled="page <= 1 || loading"
            @click="changePage(page - 1)"
          >
            Previous
          </button>
          <span aria-live="polite"
            >Page {{ page }} of {{ pages }} · {{ total }} contests</span
          >
          <button
            class="secondary-button"
            type="button"
            :disabled="page >= pages || loading"
            @click="changePage(page + 1)"
          >
            Next
          </button>
        </nav>
      </section>
    </template>
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
.manager-actions,
.contest-card-actions,
.contest-links {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.contest-list-heading {
  display: grid;
  gap: 0.75rem;
}
.contest-list-heading h2 {
  margin: 0;
}
.contest-list-heading label {
  display: grid;
  width: min(100%, 38rem);
  gap: 0.35rem;
  font-weight: 650;
}
.contest-list-heading input,
.ruleset-row select {
  width: 100%;
  min-height: 2.65rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  font: inherit;
}
.contest-list-scroll {
  max-height: 34rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: grid;
  gap: 0.5rem;
  padding: 0.25rem;
}
.contest-list-scroll:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 2px;
}
.panel {
  padding: 0.8rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.6rem;
  background: var(--color-surface);
  box-shadow: 0 4px 12px var(--color-card-shadow);
}
.contest-card {
  display: grid;
  gap: 0.5rem;
}
.contest-card h3 {
  margin: 0.25rem 0;
}
.field-help {
  margin: 0;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.contest-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.45rem 1rem;
  margin: 0;
}
.contest-meta dt {
  color: var(--color-muted);
  font-size: 0.8rem;
}
.contest-meta dd {
  margin: 0.05rem 0 0;
  overflow-wrap: anywhere;
  font-size: 0.9rem;
}
.ruleset-row {
  align-items: end;
}
.ruleset-row label {
  display: grid;
  flex: 1;
  gap: 0.35rem;
  font-weight: 650;
}
.primary-button,
.secondary-button,
.primary-link,
.file-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-height: 2.6rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  color: var(--color-brand-700);
  background: var(--color-surface);
  font: inherit;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}
.primary-button,
.primary-link {
  border-color: transparent;
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.danger-button {
  min-height: 2.6rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-error-ink);
  border-radius: 0.45rem;
  color: var(--color-error-ink);
  background: var(--color-surface);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
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
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
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
  .section-title,
  .ruleset-row {
    align-items: stretch;
    flex-direction: column;
  }
  .contest-card-actions {
    justify-content: flex-start;
  }
  .contest-meta {
    grid-template-columns: 1fr;
  }
}
</style>
