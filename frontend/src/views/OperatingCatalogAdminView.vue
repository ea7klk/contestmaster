<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiError } from '../api/client'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
import {
  createOperatingCatalogItem,
  deleteOperatingCatalogItem,
  getAdminOperatingCatalog,
  updateOperatingCatalogItem,
  type OperatingCatalogInput,
  type OperatingCatalogItem,
} from '../api/operatingCatalog'

const user = ref<PrivilegedUser | null>(null)
const items = ref<OperatingCatalogItem[]>([])
const loading = ref(true)
const denied = ref(false)
const error = ref('')
const message = ref('')
const saving = ref(false)
const editId = ref<number | null>(null)
const form = reactive<OperatingCatalogInput>({
  kind: 'band',
  key: '',
  label: '',
  description: '',
  frequency_range: null,
  sort_order: 0,
  is_active: true,
  contest_free: false,
})

function clearForm() {
  editId.value = null
  Object.assign(form, {
    kind: 'band',
    key: '',
    label: '',
    description: '',
    frequency_range: null,
    sort_order: 0,
    is_active: true,
    contest_free: false,
  })
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    user.value = await getCurrentUser()
    if (user.value.role !== 'global_administrator') {
      denied.value = true
      return
    }
    items.value = (await getAdminOperatingCatalog()).items
  } catch (cause) {
    denied.value =
      cause instanceof ApiError && [401, 403].includes(cause.statusCode ?? 0)
    if (!denied.value)
      error.value =
        cause instanceof Error ? cause.message : 'Catalog could not be loaded.'
  } finally {
    loading.value = false
  }
}

function edit(item: OperatingCatalogItem) {
  editId.value = item.id
  Object.assign(form, { ...item })
  message.value = ''
}

async function save() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    if (editId.value === null) await createOperatingCatalogItem({ ...form })
    else await updateOperatingCatalogItem(editId.value, { ...form })
    message.value =
      editId.value === null ? 'Catalog item created.' : 'Catalog item updated.'
    clearForm()
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : 'Catalog item could not be saved.'
  } finally {
    saving.value = false
  }
}

async function remove(item: OperatingCatalogItem) {
  if (
    !globalThis.confirm(
      `Delete ${item.label}? Referenced values must be deactivated instead.`,
    )
  )
    return
  try {
    await deleteOperatingCatalogItem(item.id)
    message.value = `${item.label} deleted.`
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : 'Catalog item could not be deleted.'
  }
}

onMounted(refresh)
</script>

<template>
  <section class="master-data-page" aria-labelledby="operating-catalog-heading">
    <h1 id="operating-catalog-heading">Band and mode configuration</h1>
    <p>
      Maintain shared values offered by the ruleset composer. These labels are a
      convenience catalog, not a statement of national frequency authorization.
      Contest rules decide which values apply.
    </p>
    <p v-if="denied" role="alert">Global administrator access is required.</p>
    <p v-if="error" role="alert" class="master-data-error">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="loading" role="status">Loading band and mode catalog…</p>
    <template v-else-if="!denied && user?.role === 'global_administrator'">
      <form class="catalog-editor-form" @submit.prevent="save">
        <h2>
          {{ editId === null ? 'Add catalog item' : 'Edit catalog item' }}
        </h2>
        <label
          >Type<select v-model="form.kind">
            <option value="band">Band</option>
            <option value="mode">Mode</option>
          </select></label
        >
        <label
          >Stable key<input
            v-model="form.key"
            required
            maxlength="40"
            pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
        /></label>
        <label
          >Label<input v-model="form.label" required maxlength="120"
        /></label>
        <label v-if="form.kind === 'band'"
          >Frequency reference<input
            v-model="form.frequency_range"
            maxlength="120"
            placeholder="e.g. 14 MHz"
        /></label>
        <label
          >Description<textarea
            v-model="form.description"
            maxlength="2000"
            rows="2"
          />
        </label>
        <label
          >Display order<input
            v-model.number="form.sort_order"
            type="number"
            min="0"
            max="10000"
        /></label>
        <label class="catalog-check"
          ><input v-model="form.is_active" type="checkbox" /> Active in ruleset
          composer</label
        >
        <label v-if="form.kind === 'band'" class="catalog-check"
          ><input v-model="form.contest_free" type="checkbox" /> Mark as
          contest-free (highlighted notice only)</label
        >
        <div class="catalog-actions">
          <button class="primary-button" type="submit" :disabled="saving">
            {{
              saving ? 'Saving…' : editId === null ? 'Add item' : 'Save item'
            }}
</button
          ><button class="secondary-button" type="button" @click="clearForm">
            Clear
          </button>
        </div>
      </form>
      <h2>Configured values</h2>
      <div class="master-data-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Type/value</th>
              <th>Range/description</th>
              <th>State</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in items"
              :key="item.id"
              :class="{
                'catalog-contest-free':
                  item.kind === 'band' && item.contest_free,
              }"
            >
              <td>
                <strong>{{ item.label }}</strong>
                <div>
                  {{ item.kind }} · <code>{{ item.key }}</code>
                </div>
              </td>
              <td>
                {{ item.frequency_range || '—' }}
                <div>{{ item.description }}</div>
              </td>
              <td>
                {{ item.is_active ? 'Active' : 'Inactive' }}
                <div v-if="item.contest_free" class="contest-free-label">
                  Contest-free designation
                </div>
              </td>
              <td class="master-data-actions">
                <button type="button" @click="edit(item)">Edit</button
                ><button
                  class="master-data-danger"
                  type="button"
                  @click="remove(item)"
                >
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style scoped>
.catalog-editor-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 0.8rem;
  padding: 1rem;
  margin: 1.2rem 0;
  border: 1px solid #c8d5dc;
  border-radius: 0.6rem;
}
.catalog-editor-form h2,
.catalog-actions {
  grid-column: 1 / -1;
  margin: 0;
}
.catalog-editor-form label {
  display: grid;
  gap: 0.35rem;
}
.catalog-editor-form input:not([type='checkbox']),
.catalog-editor-form select,
.catalog-editor-form textarea {
  width: 100%;
  padding: 0.55rem;
  border: 1px solid #aebfc8;
  border-radius: 0.35rem;
}
.catalog-editor-form .catalog-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.catalog-check input {
  width: 1.1rem;
  height: 1.1rem;
}
.catalog-actions {
  display: flex;
  gap: 0.5rem;
}
.catalog-contest-free {
  color: #a11414;
  background: #fff0f0;
}
.contest-free-label {
  color: #a11414;
  font-weight: 700;
}
</style>
