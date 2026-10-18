<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import {
  changeContestStatus,
  deleteContest,
  getContest,
  importContest,
  listContests,
  selectRuleset,
  type Contest,
  type ContestImportPackage,
  type ContestStatus,
} from '../api/contests'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
import { formatInteger, formatUtcDateTime } from '../i18n'
import ConfirmationModal from '../components/ConfirmationModal.vue'
import {
  getSavedRulesetVersion,
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
const exportingContestId = ref<number | null>(null)
const deletingContestId = ref<number | null>(null)
const pendingDeleteContest = ref<Contest | null>(null)
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

function removeContest(contest: Contest) {
  pendingDeleteContest.value = contest
}

async function confirmContestDeletion(value: { confirmationText: string }) {
  const contest = pendingDeleteContest.value
  if (!contest || value.confirmationText !== contest.slug) return
  deletingContestId.value = contest.id
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    await deleteContest(contest.id, value.confirmationText)
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
    pendingDeleteContest.value = null
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
    if (!isRecord(parsed) || !isRecord(parsed.contest)) {
      throw new Error('Expected a contest package with a contest object.')
    }
    if (
      parsed.ruleset !== undefined &&
      (!isRecord(parsed.ruleset) ||
        parsed.ruleset.schema_version !== 2 ||
        typeof parsed.ruleset.ruleset_key !== 'string' ||
        !Array.isArray(parsed.ruleset.rules))
    ) {
      throw new Error(
        'An included ruleset must be a schema-version-2 ruleset draft.',
      )
    }
    const result = await importContest(
      parsed as unknown as ContestImportPackage,
    )
    page.value = 1
    contestFilter.value = ''
    await refreshData()
    statusMessage.value = result.ruleset_version_id
      ? `Imported ${result.contest.name} as a draft with its ruleset assigned.`
      : `Imported ${result.contest.name} as a draft without a ruleset.`
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

async function exportContest(contest: Contest, includeRuleset: boolean) {
  exportingContestId.value = contest.id
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    const current = await getContest(contest.id)
    const packageData: ContestImportPackage = {
      contest: {
        name: current.name,
        slug: current.slug,
        description: current.description,
        starts_at: current.starts_at,
        ends_at: current.ends_at,
        periodicity: current.periodicity,
        log_submission_cutoff_at: current.log_submission_cutoff_at,
        auto_recalculate_on_upload: current.auto_recalculate_on_upload,
      },
    }
    if (includeRuleset) {
      if (current.ruleset_version_id === null) {
        throw new Error('This contest does not have an attached ruleset.')
      }
      const savedRuleset = await getSavedRulesetVersion(
        current.ruleset_version_id,
      )
      packageData.ruleset = savedRuleset.configuration
    }
    const blob = new Blob([`${JSON.stringify(packageData, null, 2)}\n`], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${current.slug}${includeRuleset ? '' : '-contest-only'}.json`
    document.body.append(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    statusMessage.value = includeRuleset
      ? `Exported ${current.name} with its ruleset.`
      : `Exported ${current.name} without its ruleset.`
  } catch (error) {
    errorMessage.value =
      error instanceof Error
        ? error.message
        : 'The contest could not be exported.'
  } finally {
    exportingContestId.value = null
  }
}

onMounted(refreshData)
</script>

<template>
  <section class="manager-page" aria-labelledby="manager-title">
    <div class="manager-heading">
      <div>
        <p class="eyebrow">{{ $tr('Contest staff') }}</p>
        <h1 id="manager-title">{{ $tr('Contest manager') }}</h1>
        <p v-if="user" class="intro">
          {{ $tr('Signed in as') }} {{ user.display_name }} ({{
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
          {{ $tr('Create a contest') }}
        </RouterLink>
        <RouterLink class="secondary-button" to="/manage/rulesets">
          {{ $tr('Manage rulesets') }}
        </RouterLink>
      </div>
    </div>

    <p v-if="loading" role="status" class="notice">
      {{ $tr('Loading your contests…') }}
    </p>
    <section
      v-else-if="forbidden"
      class="panel"
      aria-labelledby="sign-in-required"
    >
      <h2 id="sign-in-required">{{ $tr('Sign-in required') }}</h2>
      <p>
        {{
          $tr(
            'Sign in with a contest-manager or global-administrator account to manage contests.',
          )
        }}
      </p>
      <RouterLink class="primary-link" to="/sign-in?next=/manage/contests">
        {{ $tr('Sign in') }}
      </RouterLink>
    </section>
    <template v-else>
      <p v-if="errorMessage" class="error-panel" role="alert">
        {{ errorMessage }}
      </p>
      <p v-if="statusMessage" class="success-panel" role="status">
        {{ $tr(statusMessage) }}
      </p>
      <p class="field-help">
        {{
          $tr(
            'Import a JSON package with contest metadata and an optional schema-version-2 ruleset draft. The imported contest starts as a draft.',
          )
        }}
      </p>
      <section class="contest-list" aria-labelledby="contest-list-title">
        <div class="contest-list-heading">
          <h2 id="contest-list-title">{{ $tr('Your contests') }}</h2>
          <label for="contest-filter"
            >{{ $tr('Filter contests') }}
            <input
              id="contest-filter"
              v-model="contestFilter"
              type="search"
              maxlength="120"
              autocomplete="off"
              :placeholder="$tr('Name, slug, or status')"
              aria-describedby="contest-filter-help"
              @input="applyFilter"
            />
            <span id="contest-filter-help" class="field-help">{{
              $tr('Search by contest name, URL slug, or exact status.')
            }}</span>
          </label>
        </div>
        <p v-if="total === 0 && !contestFilter" class="notice">
          {{ $tr('You have not created a contest yet.') }}
        </p>
        <p
          v-else-if="filteredContests.length === 0"
          class="notice"
          role="status"
        >
          {{ $tr('No contests match “') }}{{ contestFilter }}”.
        </p>
        <div v-else class="contest-card-list">
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
                <details class="export-actions">
                  <summary>{{ $tr('Export contest') }}</summary>
                  <div class="export-action-options">
                    <button
                      class="secondary-button"
                      type="button"
                      :disabled="exportingContestId === contest.id"
                      @click="exportContest(contest, false)"
                    >
                      {{ $tr('Contest only') }}
                    </button>
                    <button
                      class="secondary-button"
                      type="button"
                      :disabled="
                        contest.ruleset_version_id === null ||
                        exportingContestId === contest.id
                      "
                      @click="exportContest(contest, true)"
                    >
                      {{ $tr('Contest with ruleset') }}
                    </button>
                  </div>
                </details>
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
                  {{ $tr('Edit details') }}
                </RouterLink>
                <RouterLink
                  v-if="
                    contest.series_id !== null &&
                    contest.series_id !== undefined
                  "
                  class="secondary-button"
                  :to="`/manage/contests/${contest.id}/edit`"
                >
                  {{ $tr('Manage series') }}
                </RouterLink>
                <button
                  v-else
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
              {{
                $tr(
                  'Opening makes this contest public and eligible for log submissions.',
                )
              }}
            </p>
            <div class="contest-links">
              <span>
                <RouterLink :to="`/manage/contests/${contest.id}/results`">{{
                  $tr('Generate and publish results')
                }}</RouterLink>
              </span>
              <span>
                <RouterLink :to="`/manage/contests/${contest.id}/entries`">{{
                  $tr('Submitted logs')
                }}</RouterLink>
              </span>
            </div>
            <dl class="contest-meta">
              <div>
                <dt>{{ $tr('Starts') }}</dt>
                <dd>{{ formatUtcDateTime(contest.starts_at) }}</dd>
              </div>
              <div>
                <dt>{{ $tr('Ends') }}</dt>
                <dd>{{ formatUtcDateTime(contest.ends_at) }}</dd>
              </div>
              <div>
                <dt>{{ $tr('Log cutoff') }}</dt>
                <dd>
                  {{ formatUtcDateTime(contest.log_submission_cutoff_at) }}
                </dd>
              </div>
              <div>
                <dt>{{ $tr('Automatic recalculation') }}</dt>
                <dd>{{ contest.auto_recalculate_on_upload ? 'On' : 'Off' }}</dd>
              </div>
            </dl>
            <div class="ruleset-row">
              <label :for="`ruleset-${contest.id}`"
                >{{ $tr('Ruleset and category definition') }}
                <select
                  :id="`ruleset-${contest.id}`"
                  v-model="rulesetSelections[contest.id]"
                  :disabled="
                    contest.status !== 'draft' || rulesets.length === 0
                  "
                >
                  <option value="">{{ $tr('Select a saved ruleset') }}</option>
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
                {{ $tr('Edit ruleset') }}
              </RouterLink>
            </div>
            <p v-if="contest.ruleset_version_id === null" class="field-help">
              {{
                $tr(
                  'This draft needs a validated ruleset before it can be opened.',
                )
              }}
            </p>
          </article>
        </div>
        <nav
          v-if="pages > 1"
          class="pagination"
          :aria-label="$tr('Contest list pages')"
        >
          <button
            class="secondary-button"
            type="button"
            :disabled="page <= 1 || loading"
            @click="changePage(page - 1)"
          >
            {{ $tr('Previous') }}
          </button>
          <span aria-live="polite"
            >{{ $tr('Page') }} {{ page }} {{ $tr('of') }} {{ pages }} ·
            {{ formatInteger(total) }} {{ $tr('contests') }}</span
          >
          <button
            class="secondary-button"
            type="button"
            :disabled="page >= pages || loading"
            @click="changePage(page + 1)"
          >
            {{ $tr('Next') }}
          </button>
        </nav>
      </section>
    </template>
    <ConfirmationModal
      :open="pendingDeleteContest !== null"
      :title="$tr('Delete {name}?', { name: pendingDeleteContest?.name ?? '' })"
      :description="
        $tr(
          'This permanently deletes the contest, its uploaded logs, scores, published results, and contest history. This action cannot be undone.',
        )
      "
      :confirm-label="$tr('Delete contest')"
      :required-text="pendingDeleteContest?.slug ?? ''"
      :required-text-label="
        $tr('Type {value} to confirm.', {
          value: pendingDeleteContest?.slug ?? '',
        })
      "
      :busy="deletingContestId !== null"
      @confirm="confirmContestDeletion"
      @cancel="pendingDeleteContest = null"
    />
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
.contest-card-list {
  display: grid;
  gap: 0.5rem;
}
.export-actions {
  position: relative;
}
.export-actions summary {
  cursor: pointer;
  font-weight: 650;
}
.export-action-options {
  position: absolute;
  z-index: 2;
  right: 0;
  display: grid;
  gap: 0.35rem;
  min-width: 12rem;
  padding: 0.5rem;
  border: 1px solid var(--color-border);
  border-radius: 0.45rem;
  background: var(--color-surface);
  box-shadow: 0 4px 12px var(--color-card-shadow);
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
