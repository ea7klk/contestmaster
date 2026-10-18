<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ApiError } from '../api/client'
import {
  createBand,
  createMode,
  deleteBand,
  deleteMode,
  getAdminBands,
  getAdminModes,
  updateBand,
  updateMode,
  type BandCatalogInput,
  type BandCatalogItem,
  type ModeCatalogInput,
  type ModeCatalogItem,
} from '../api/operatingCatalog'
import { getCurrentUser, type PrivilegedUser } from '../api/identity'
import ConfirmationModal from '../components/ConfirmationModal.vue'
import KeyboardScrollRegion from '../components/KeyboardScrollRegion.vue'

const bands = ref<BandCatalogItem[]>([])
const modes = ref<ModeCatalogItem[]>([])
const user = ref<PrivilegedUser | null>(null)
const loading = ref(true)
const saving = ref(false)
const denied = ref(false)
const error = ref('')
const message = ref('')
const editingBandId = ref<number | null>(null)
const editingModeId = ref<number | null>(null)
const pendingDelete = ref<
  | { kind: 'band'; item: BandCatalogItem }
  | { kind: 'mode'; item: ModeCatalogItem }
  | null
>(null)
const bandForm = reactive<BandCatalogInput>({
  key: '',
  label: '',
  description: '',
  frequency_range: null,
  sort_order: 0,
  is_active: true,
  contest_free: false,
})
const modeForm = reactive<ModeCatalogInput>({
  key: '',
  label: '',
  description: '',
  sort_order: 0,
  is_active: true,
})

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    user.value = await getCurrentUser()
    if (user.value.role !== 'global_administrator') {
      denied.value = true
      return
    }
    const [bandResponse, modeResponse] = await Promise.all([
      getAdminBands(),
      getAdminModes(),
    ])
    bands.value = bandResponse.items
    modes.value = modeResponse.items
  } catch (cause) {
    denied.value =
      cause instanceof ApiError && [401, 403].includes(cause.statusCode ?? 0)
    if (!denied.value)
      error.value =
        cause instanceof Error ? cause.message : 'Catalogs could not be loaded.'
  } finally {
    loading.value = false
  }
}

function clearBandForm() {
  editingBandId.value = null
  Object.assign(bandForm, {
    key: '',
    label: '',
    description: '',
    frequency_range: null,
    sort_order: 0,
    is_active: true,
    contest_free: false,
  })
}

function clearModeForm() {
  editingModeId.value = null
  Object.assign(modeForm, {
    key: '',
    label: '',
    description: '',
    sort_order: 0,
    is_active: true,
  })
}

function editBand(item: BandCatalogItem) {
  editingBandId.value = item.id
  Object.assign(bandForm, item)
  message.value = ''
}

function editMode(item: ModeCatalogItem) {
  editingModeId.value = item.id
  Object.assign(modeForm, item)
  message.value = ''
}

async function saveBand() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    if (editingBandId.value === null) await createBand({ ...bandForm })
    else await updateBand(editingBandId.value, { ...bandForm })
    message.value =
      editingBandId.value === null ? 'Band added.' : 'Band updated.'
    clearBandForm()
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof Error ? cause.message : 'Band could not be saved.'
  } finally {
    saving.value = false
  }
}

async function saveMode() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    if (editingModeId.value === null) await createMode({ ...modeForm })
    else await updateMode(editingModeId.value, { ...modeForm })
    message.value =
      editingModeId.value === null ? 'Mode added.' : 'Mode updated.'
    clearModeForm()
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof Error ? cause.message : 'Mode could not be saved.'
  } finally {
    saving.value = false
  }
}

function removeBand(item: BandCatalogItem) {
  pendingDelete.value = { kind: 'band', item }
}

function removeMode(item: ModeCatalogItem) {
  pendingDelete.value = { kind: 'mode', item }
}

async function confirmDelete() {
  const deletion = pendingDelete.value
  if (!deletion) return
  try {
    if (deletion.kind === 'band') await deleteBand(deletion.item.id)
    else await deleteMode(deletion.item.id)
    message.value = `${deletion.item.label} deleted.`
    pendingDelete.value = null
    await refresh()
  } catch (cause) {
    error.value =
      cause instanceof Error
        ? cause.message
        : `${deletion.kind === 'band' ? 'Band' : 'Mode'} could not be deleted.`
  } finally {
    pendingDelete.value = null
  }
}

onMounted(refresh)
</script>

<template>
  <section class="master-data-page" aria-labelledby="operating-catalog-heading">
    <h1 id="operating-catalog-heading">{{ $tr('Bands and modes') }}</h1>
    <p>
      {{
        $tr(
          'Maintain shared values offered by the ruleset composer. These catalogs do not describe national frequency authorization; each contest’s published rules decide which values apply.',
        )
      }}
    </p>
    <p v-if="denied" role="alert">
      {{ $tr('Global administrator access is required.') }}
    </p>
    <p v-if="error" role="alert" class="master-data-error">{{ $tr(error) }}</p>
    <p v-if="message" role="status">{{ $tr(message) }}</p>
    <p v-if="loading" role="status">{{ $tr('Loading bands and modes…') }}</p>
    <template v-else-if="!denied && user?.role === 'global_administrator'">
      <section class="catalog-section" aria-labelledby="bands-heading">
        <h2 id="bands-heading">{{ $tr('Bands') }}</h2>
        <form class="catalog-editor-form" @submit.prevent="saveBand">
          <h3>
            {{ editingBandId === null ? 'Add catalog item' : 'Edit band' }}
          </h3>
          <label
            >{{ $tr('Stable key')
            }}<input
              v-model="bandForm.key"
              required
              maxlength="40"
              pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
          /></label>
          <label
            >{{ $tr('Label')
            }}<input v-model="bandForm.label" required maxlength="120"
          /></label>
          <label
            >{{ $tr('Frequency reference')
            }}<input
              v-model="bandForm.frequency_range"
              maxlength="120"
              :placeholder="$tr('e.g. 14 MHz')"
          /></label>
          <label
            >{{ $tr('Description')
            }}<textarea
              v-model="bandForm.description"
              maxlength="2000"
              rows="2"
            />
          </label>
          <label
            >{{ $tr('Display order')
            }}<input
              v-model.number="bandForm.sort_order"
              type="number"
              min="0"
              max="10000"
          /></label>
          <label class="catalog-check"
            ><input v-model="bandForm.is_active" type="checkbox" />
            {{ $tr('Active in ruleset composer') }}</label
          >
          <label class="catalog-check"
            ><input v-model="bandForm.contest_free" type="checkbox" />
            {{ $tr('Mark as contest-free (highlighted notice only)') }}</label
          >
          <div class="catalog-actions">
            <button class="primary-button" type="submit" :disabled="saving">
              {{
                saving
                  ? 'Saving…'
                  : editingBandId === null
                    ? 'Add band'
                    : 'Save band'
              }}
            </button>
            <button
              class="secondary-button"
              type="button"
              @click="clearBandForm"
            >
              {{ $tr('Clear') }}
            </button>
          </div>
        </form>
        <KeyboardScrollRegion
          class="master-data-table-wrap"
          label="Configured bands"
        >
          <table>
            <thead>
              <tr>
                <th>{{ $tr('Band') }}</th>
                <th>{{ $tr('Frequency reference') }}</th>
                <th>{{ $tr('Description') }}</th>
                <th>{{ $tr('State') }}</th>
                <th>{{ $tr('Actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in bands"
                :key="item.id"
                :class="{ 'catalog-contest-free': item.contest_free }"
              >
                <td>
                  <strong>{{ item.label }}</strong>
                  <div>
                    <code>{{ item.key }}</code>
                  </div>
                </td>
                <td>{{ item.frequency_range || '—' }}</td>
                <td>{{ item.description || '—' }}</td>
                <td>
                  {{ item.is_active ? 'Active' : 'Inactive' }}
                  <div v-if="item.contest_free" class="contest-free-label">
                    {{ $tr('No-contest band (advisory)') }}
                  </div>
                </td>
                <td class="master-data-actions">
                  <button type="button" @click="editBand(item)">
                    {{ $tr('Edit') }}
                  </button>
                  <button
                    class="master-data-danger"
                    type="button"
                    @click="removeBand(item)"
                  >
                    {{ $tr('Delete') }}
                  </button>
                </td>
              </tr>
              <tr v-if="bands.length === 0">
                <td colspan="5">{{ $tr('No bands configured.') }}</td>
              </tr>
            </tbody>
          </table>
        </KeyboardScrollRegion>
      </section>

      <section class="catalog-section" aria-labelledby="modes-heading">
        <h2 id="modes-heading">{{ $tr('Modes') }}</h2>
        <form class="catalog-editor-form" @submit.prevent="saveMode">
          <h3>
            {{ editingModeId === null ? 'Add catalog item' : 'Edit mode' }}
          </h3>
          <label
            >{{ $tr('Stable key')
            }}<input
              v-model="modeForm.key"
              required
              maxlength="40"
              pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
          /></label>
          <label
            >{{ $tr('Label')
            }}<input v-model="modeForm.label" required maxlength="120"
          /></label>
          <label
            >{{ $tr('Description')
            }}<textarea
              v-model="modeForm.description"
              maxlength="2000"
              rows="2"
            />
          </label>
          <label
            >{{ $tr('Display order')
            }}<input
              v-model.number="modeForm.sort_order"
              type="number"
              min="0"
              max="10000"
          /></label>
          <label class="catalog-check"
            ><input v-model="modeForm.is_active" type="checkbox" />
            {{ $tr('Active in ruleset composer') }}</label
          >
          <div class="catalog-actions">
            <button class="primary-button" type="submit" :disabled="saving">
              {{
                saving
                  ? 'Saving…'
                  : editingModeId === null
                    ? 'Add mode'
                    : 'Save mode'
              }}
            </button>
            <button
              class="secondary-button"
              type="button"
              @click="clearModeForm"
            >
              {{ $tr('Clear') }}
            </button>
          </div>
        </form>
        <KeyboardScrollRegion
          class="master-data-table-wrap"
          label="Configured modes"
        >
          <table>
            <thead>
              <tr>
                <th>{{ $tr('Mode') }}</th>
                <th>{{ $tr('Description') }}</th>
                <th>{{ $tr('State') }}</th>
                <th>{{ $tr('Actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in modes" :key="item.id">
                <td>
                  <strong>{{ item.label }}</strong>
                  <div>
                    <code>{{ item.key }}</code>
                  </div>
                </td>
                <td>{{ item.description || '—' }}</td>
                <td>{{ item.is_active ? 'Active' : 'Inactive' }}</td>
                <td class="master-data-actions">
                  <button type="button" @click="editMode(item)">
                    {{ $tr('Edit') }}
                  </button>
                  <button
                    class="master-data-danger"
                    type="button"
                    @click="removeMode(item)"
                  >
                    {{ $tr('Delete') }}
                  </button>
                </td>
              </tr>
              <tr v-if="modes.length === 0">
                <td colspan="4">{{ $tr('No modes configured.') }}</td>
              </tr>
            </tbody>
          </table>
        </KeyboardScrollRegion>
      </section>
    </template>
    <ConfirmationModal
      :open="pendingDelete !== null"
      :title="$tr('Delete {name}?', { name: pendingDelete?.item.label ?? '' })"
      :description="
        $tr(
          'Referenced values must be deactivated instead. This action cannot be undone.',
        )
      "
      :confirm-label="$tr('Delete')"
      @confirm="confirmDelete"
      @cancel="pendingDelete = null"
    />
  </section>
</template>

<style scoped>
.catalog-section + .catalog-section {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 2px solid var(--color-border);
}
.catalog-section > h2 {
  margin-bottom: 0.8rem;
  color: var(--color-brand-900);
}
.catalog-editor-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 0.8rem;
  margin-bottom: 1rem;
  padding: 1rem;
  border: 1px solid var(--color-border);
  border-radius: 0.55rem;
  background: var(--color-surface-muted);
}
.catalog-editor-form h3 {
  grid-column: 1 / -1;
  margin: 0;
}
.catalog-editor-form label {
  display: grid;
  gap: 0.35rem;
  color: var(--color-muted);
  font-weight: 650;
}
.catalog-editor-form .catalog-check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.catalog-editor-form .catalog-check input {
  width: 1.15rem;
  min-height: 1.15rem;
  accent-color: var(--color-brand-700);
}
.catalog-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 0.5rem;
}
.catalog-contest-free {
  color: var(--color-error-ink);
  background: var(--color-error-surface);
}
.contest-free-label {
  font-size: 0.78rem;
  font-weight: 700;
}
</style>
