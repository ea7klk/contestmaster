<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import { searchAuditEvents, type AuditEventRecord } from '../api/audit'
import { formatUtcDateTime } from '../i18n'

const items = ref<AuditEventRecord[]>([])
const query = ref('')
const action = ref<string[]>([])
const targetType = ref<string[]>([])
const actionOptions = ref<string[]>([])
const targetTypeOptions = ref<string[]>([])
const fromLocal = ref('')
const toLocal = ref('')
const page = ref(1)
const pageSize = 50
const total = ref(0)
const loading = ref(false)
const denied = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  denied.value = false
  try {
    const response = await searchAuditEvents({
      q: query.value.trim() || undefined,
      action: action.value.length ? action.value : undefined,
      target_type: targetType.value.length ? targetType.value : undefined,
      from_at: fromLocal.value
        ? new Date(fromLocal.value).toISOString()
        : undefined,
      to_at: toLocal.value ? new Date(toLocal.value).toISOString() : undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = response.items
    total.value = response.total
    actionOptions.value = response.action_options
    targetTypeOptions.value = response.target_type_options
  } catch (cause) {
    denied.value =
      cause instanceof ApiError && [401, 403].includes(cause.statusCode ?? 0)
    error.value = denied.value
      ? 'Global administrator access is required.'
      : cause instanceof ApiError
        ? cause.message
        : 'The audit log could not be loaded.'
  } finally {
    loading.value = false
  }
}

async function search() {
  page.value = 1
  await load()
}

async function changePage(next: number) {
  page.value = next
  await load()
}

function displayDate(value: string) {
  return formatUtcDateTime(value)
}

onMounted(load)
</script>

<template>
  <section class="audit-page" aria-labelledby="audit-heading">
    <header class="audit-header">
      <div>
        <h1 id="audit-heading">{{ $tr('Audit log') }}</h1>
        <p>
          {{
            $tr(
              'Administrative activity and result calculations from the last 90 days.',
            )
          }}
        </p>
      </div>
    </header>

    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <form v-if="!denied" class="audit-filters" @submit.prevent="search">
      <label for="audit-search"
        >{{ $tr('Search audit events') }}
        <input
          id="audit-search"
          v-model="query"
          type="search"
          maxlength="200"
        />
      </label>
      <label for="audit-action"
        >{{ $tr('Action') }}
        <select id="audit-action" v-model="action" multiple size="4">
          <option v-for="option in actionOptions" :key="option" :value="option">
            {{ option }}
          </option>
        </select>
      </label>
      <label for="audit-target"
        >{{ $tr('Target type') }}
        <select id="audit-target" v-model="targetType" multiple size="4">
          <option
            v-for="option in targetTypeOptions"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
        </select>
      </label>
      <label for="audit-from"
        >{{ $tr('From (your local time)') }}
        <input id="audit-from" v-model="fromLocal" type="datetime-local" />
      </label>
      <label for="audit-to"
        >{{ $tr('To (your local time)') }}
        <input id="audit-to" v-model="toLocal" type="datetime-local" />
      </label>
      <button class="primary-button" type="submit" :disabled="loading">
        {{ $tr('Search') }}
      </button>
    </form>

    <p v-if="loading" role="status">{{ $tr('Loading audit events…') }}</p>
    <p v-else-if="!denied && items.length === 0" role="status">
      {{ $tr('No audit events match these filters.') }}
    </p>
    <div v-if="!denied && items.length" class="table-scroll audit-table-scroll">
      <table class="audit-table">
        <thead>
          <tr>
            <th>{{ $tr('When (UTC)') }}</th>
            <th>{{ $tr('Actor') }}</th>
            <th>{{ $tr('Action') }}</th>
            <th>{{ $tr('Target') }}</th>
            <th>{{ $tr('Reason') }}</th>
            <th>{{ $tr('Details') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="event in items" :key="event.id">
            <td>{{ displayDate(event.occurred_at) }}</td>
            <td>
              {{
                event.actor ||
                (event.actor_user_id
                  ? `User #${event.actor_user_id}`
                  : $tr(
                      event.metadata.actor_kind === 'participant' ||
                        event.metadata.received_via === 'participant_session'
                        ? 'Participant'
                        : 'System or guest',
                    ))
              }}
            </td>
            <td>
              <code>{{ event.action }}</code>
            </td>
            <td>
              <div>{{ event.target_type }}</div>
              <small>{{ event.target_name }}</small>
            </td>
            <td>{{ event.reason || '—' }}</td>
            <td>
              <details>
                <summary>{{ $tr('View details') }}</summary>
                <pre>{{ JSON.stringify(event.metadata, null, 2) }}</pre>
                <small v-if="event.request_id"
                  >{{ $tr('Request ID') }}: {{ event.request_id }}</small
                >
              </details>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <nav
      v-if="!denied && total > pageSize"
      class="audit-pagination"
      :aria-label="$tr('Audit log pages')"
    >
      <button
        class="secondary-button"
        type="button"
        :disabled="page <= 1 || loading"
        @click="changePage(page - 1)"
      >
        {{ $tr('Previous') }}
      </button>
      <span>{{
        $tr('Page {page} of {pages}', {
          page,
          pages: Math.ceil(total / pageSize),
        })
      }}</span>
      <button
        class="secondary-button"
        type="button"
        :disabled="page * pageSize >= total || loading"
        @click="changePage(page + 1)"
      >
        {{ $tr('Next') }}
      </button>
    </nav>
  </section>
</template>

<style scoped>
.audit-page {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.audit-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: start;
}
.audit-filters {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr));
  gap: 0.85rem;
  align-items: end;
  margin: 1.25rem 0;
}
.audit-filters label {
  display: grid;
  gap: 0.35rem;
  font-weight: 650;
  min-width: 0;
}
.audit-filters input,
.audit-filters select {
  width: 100%;
  min-width: 0;
}
.audit-table-scroll {
  max-height: none;
}
.audit-table {
  width: 100%;
  border-collapse: collapse;
}
.audit-table th,
.audit-table td {
  padding: 0.65rem;
  border-bottom: 1px solid var(--border-color, #c9c1bb);
  text-align: left;
  vertical-align: top;
}
.audit-table pre {
  max-width: 36rem;
  max-height: 18rem;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.audit-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin-top: 1.25rem;
}
@media (max-width: 42rem) {
  .audit-table {
    min-width: 58rem;
  }
}
</style>
