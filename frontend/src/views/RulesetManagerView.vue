<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ApiError } from '../api/client'
import {
  deleteSavedRulesetVersion,
  getSavedRulesetVersion,
  listRulesetVersions,
  type SavedRulesetVersion,
} from '../api/rulesets'
import { getCurrentUser } from '../api/identity'
import { formatInteger } from '../i18n'
import ConfirmationModal from '../components/ConfirmationModal.vue'

const pageSize = 20
const items = ref<SavedRulesetVersion[]>([])
const page = ref(1)
const pages = ref(0)
const total = ref(0)
const query = ref('')
const loading = ref(true)
const forbidden = ref(false)
const error = ref('')
const message = ref('')
const deletingId = ref<number | null>(null)
const pendingDelete = ref<SavedRulesetVersion | null>(null)
const exportingId = ref<number | null>(null)
const filteredItems = computed(() => items.value)

async function refresh() {
  loading.value = true
  error.value = ''
  forbidden.value = false
  try {
    await getCurrentUser()
    const response = await listRulesetVersions(
      page.value,
      pageSize,
      query.value,
    )
    items.value = response.items
    pages.value = response.meta.pages
    total.value = response.meta.total
  } catch (cause) {
    if (cause instanceof ApiError && cause.statusCode === 401)
      forbidden.value = true
    else
      error.value =
        cause instanceof Error
          ? cause.message
          : 'Saved rulesets could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function filter() {
  page.value = 1
  await refresh()
}

async function changePage(next: number) {
  if (next < 1 || next > pages.value || next === page.value) return
  page.value = next
  await refresh()
}

function remove(saved: SavedRulesetVersion) {
  if (!saved.can_delete) return
  pendingDelete.value = saved
}

async function confirmDelete(value: { confirmationText: string }) {
  const saved = pendingDelete.value
  if (!saved) return
  const identity = `${saved.ruleset_key}@${saved.version}`
  if (value.confirmationText !== identity) return
  deletingId.value = saved.id
  error.value = ''
  message.value = ''
  try {
    await deleteSavedRulesetVersion(saved.id, value.confirmationText)
    if (items.value.length === 1 && page.value > 1) page.value -= 1
    await refresh()
    message.value = `Deleted unused ruleset ${identity}.`
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : 'The ruleset version could not be deleted.'
  } finally {
    deletingId.value = null
    pendingDelete.value = null
  }
}

async function exportRuleset(saved: SavedRulesetVersion) {
  exportingId.value = saved.id
  error.value = ''
  try {
    const { configuration } = await getSavedRulesetVersion(saved.id)
    const blob = new Blob([`${JSON.stringify(configuration, null, 2)}\n`], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const filenameKey = saved.ruleset_key.replace(/[^a-z0-9_-]+/gi, '-')
    const filenameVersion = saved.version.replace(/[^a-z0-9_.-]+/gi, '-')
    link.href = url
    link.download = `${filenameKey}-${filenameVersion}.json`
    link.click()
    URL.revokeObjectURL(url)
    message.value = `Exported ${saved.ruleset_key} version ${saved.version}.`
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : 'The ruleset version could not be exported.'
  } finally {
    exportingId.value = null
  }
}

onMounted(refresh)
</script>

<template>
  <section class="ruleset-list-page" aria-labelledby="ruleset-list-title">
    <div class="heading">
      <div>
        <p class="eyebrow">{{ $tr('Contest manager tools') }}</p>
        <h1 id="ruleset-list-title">{{ $tr('Rulesets') }}</h1>
        <p>
          {{
            $tr(
              'Browse immutable ruleset versions, create a new ruleset, or start a revised version from an existing one.',
            )
          }}
        </p>
      </div>
      <div class="actions">
        <span>
          <RouterLink
            class="secondary-button"
            to="/manage/rulesets/new#import-ruleset"
            >{{ $tr('Import ruleset') }}</RouterLink
          >
        </span>
        <span>
          <RouterLink class="secondary-button" to="/manage/contests">{{
            $tr('Manage contests')
          }}</RouterLink>
        </span>
        <span>
          <RouterLink class="primary-button" to="/manage/rulesets/new">{{
            $tr('Create ruleset')
          }}</RouterLink>
        </span>
      </div>
    </div>
    <p v-if="loading" role="status" class="notice">
      {{ $tr('Loading saved rulesets…') }}
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
            'Sign in with a contest-manager or global-administrator account to manage rulesets.',
          )
        }}
      </p>
      <RouterLink class="primary-button" to="/sign-in?next=/manage/rulesets">
        {{ $tr('Sign in') }}
      </RouterLink>
    </section>
    <template v-else>
      <p v-if="error" role="alert" class="error-panel">{{ $tr(error) }}</p>
      <p v-if="message" role="status" class="success-panel">
        {{ $tr(message) }}
      </p>
      <label class="filter"
        >{{ $tr('Filter rulesets') }}
        <input
          v-model="query"
          type="search"
          maxlength="120"
          :placeholder="$tr('Ruleset key, version, or source edition')"
          autocomplete="off"
          @input="filter"
        />
      </label>
      <p v-if="total === 0 && !query" class="notice">
        {{ $tr('No saved ruleset versions are available yet.') }}
      </p>
      <p v-else-if="filteredItems.length === 0" role="status" class="notice">
        {{ $tr('No rulesets match “') }}{{ query }}”.
      </p>
      <ul v-else class="list" :aria-label="$tr('Saved ruleset versions')">
        <li v-for="saved in filteredItems" :key="saved.id" class="panel row">
          <div class="details">
            <h2>
              {{ saved.ruleset_key }} {{ $tr('· version') }} {{ saved.version }}
            </h2>
            <p>
              {{ saved.source_edition || 'No source edition' }} ·
              {{ saved.rule_type_keys.length }} {{ $tr('rule types') }}
            </p>
            <p class="rule-types">{{ saved.rule_type_keys.join(', ') }}</p>
          </div>
          <div class="row-actions">
            <button
              class="secondary-button"
              type="button"
              :disabled="exportingId === saved.id"
              @click="exportRuleset(saved)"
            >
              {{ exportingId === saved.id ? 'Exporting…' : 'Export ruleset' }}
            </button>
            <span>
              <RouterLink
                class="secondary-button"
                :to="`/manage/rulesets/${saved.id}/edit`"
                >{{ $tr('Create version from this ruleset') }}</RouterLink
              >
            </span>
            <button
              v-if="saved.can_delete"
              class="danger-button"
              type="button"
              :disabled="deletingId === saved.id"
              @click="remove(saved)"
            >
              {{
                deletingId === saved.id ? 'Deleting…' : 'Delete unused version'
              }}
            </button>
          </div>
        </li>
      </ul>
      <nav
        v-if="pages > 1"
        class="pagination"
        :aria-label="$tr('Ruleset list pages')"
      >
        <span>
          <button
            class="secondary-button"
            type="button"
            :disabled="page <= 1 || loading"
            @click="changePage(page - 1)"
          >
            {{ $tr('Previous') }}
          </button>
        </span>
        <span aria-live="polite"
          >{{ $tr('Page') }} {{ page }} {{ $tr('of') }} {{ pages }} ·
          {{ formatInteger(total) }} {{ $tr('rulesets') }}</span
        >
        <span>
          <button
            class="secondary-button"
            type="button"
            :disabled="page >= pages || loading"
            @click="changePage(page + 1)"
          >
            {{ $tr('Next') }}
          </button>
        </span>
      </nav>
    </template>
    <ConfirmationModal
      :open="pendingDelete !== null"
      :title="
        $tr('Delete saved ruleset {name}?', {
          name: pendingDelete
            ? `${pendingDelete.ruleset_key}@${pendingDelete.version}`
            : '',
        })
      "
      :description="
        $tr(
          'Only ruleset versions not referenced by contests or score history can be deleted. This action cannot be undone.',
        )
      "
      :confirm-label="$tr('Delete ruleset')"
      :required-text="
        pendingDelete
          ? `${pendingDelete.ruleset_key}@${pendingDelete.version}`
          : ''
      "
      :required-text-label="
        $tr('Type {value} to confirm.', {
          value: pendingDelete
            ? `${pendingDelete.ruleset_key}@${pendingDelete.version}`
            : '',
        })
      "
      :busy="deletingId !== null"
      @confirm="confirmDelete"
      @cancel="pendingDelete = null"
    />
  </section>
</template>

<style scoped>
.ruleset-list-page {
  display: grid;
  gap: 1rem;
}
.heading,
.row,
.actions,
.row-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.heading h1 {
  margin: 0.25rem 0;
}
.heading p {
  max-width: 54rem;
}
.actions,
.row-actions {
  flex-wrap: wrap;
}
.filter {
  display: grid;
  width: min(100%, 38rem);
  gap: 0.35rem;
  font-weight: 650;
}
.filter input {
  min-height: 2.65rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--color-border-strong);
  border-radius: 0.45rem;
  font: inherit;
}
.list {
  display: grid;
  gap: 0.55rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.panel {
  padding: 0.85rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.65rem;
  background: var(--color-surface);
  box-shadow: 0 4px 12px var(--color-card-shadow);
}
.details h2 {
  margin: 0;
  font-size: 1.05rem;
}
.details p {
  margin: 0.25rem 0 0;
  color: var(--color-muted);
}
.rule-types {
  font-size: 0.9rem;
}
.primary-button,
.secondary-button,
.danger-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
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
.primary-button {
  border-color: transparent;
  color: var(--color-surface);
  background: var(--color-brand-700);
}
.danger-button {
  color: var(--color-error-ink);
  border-color: var(--color-error-ink);
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
  .heading,
  .row {
    align-items: stretch;
    flex-direction: column;
  }
  .row-actions,
  .actions {
    justify-content: flex-start;
  }
}
</style>
