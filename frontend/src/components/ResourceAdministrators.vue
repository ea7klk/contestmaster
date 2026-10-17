<script setup lang="ts">
import { ref, watch } from 'vue'
import { ApiError } from '../api/client'
import { getCurrentUser } from '../api/identity'
import {
  addResourceAdministrator,
  getResourceAdministrators,
  removeResourceAdministrator,
  type ResourceAdministratorList,
} from '../api/resourceAdministrators'

const props = defineProps<{ resourceKind: 'contest' | 'ruleset'; resourceId: number | null }>()
const data = ref<ResourceAdministratorList | null>(null)
const canEdit = ref(false)
const selectedUserId = ref('')
const busy = ref(false)
const error = ref('')

async function load() {
  if (props.resourceId === null) return
  busy.value = true
  error.value = ''
  try {
    const [user, access] = await Promise.all([
      getCurrentUser(),
      getResourceAdministrators(props.resourceKind, props.resourceId),
    ])
    data.value = access
    canEdit.value = user.role === 'global_administrator' || user.id === access.owner_user_id
  }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'Administrator assignments could not be loaded.' }
  finally { busy.value = false }
}

async function add() {
  if (props.resourceId === null || !selectedUserId.value) return
  busy.value = true
  error.value = ''
  try {
    await addResourceAdministrator(props.resourceKind, props.resourceId, Number(selectedUserId.value))
    selectedUserId.value = ''
    await load()
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'The administrator could not be assigned.' }
  finally { busy.value = false }
}

async function remove(userId: number) {
  if (props.resourceId === null) return
  busy.value = true
  error.value = ''
  try { await removeResourceAdministrator(props.resourceKind, props.resourceId, userId); await load() }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'The administrator assignment could not be removed.' }
  finally { busy.value = false }
}

watch(() => [props.resourceKind, props.resourceId] as const, load, { immediate: true })
</script>

<template>
  <section v-if="resourceId !== null" class="panel" aria-labelledby="resource-admin-heading">
    <h2 id="resource-admin-heading">{{ $tr('Resource administrators') }}</h2>
    <p>{{ $tr('The creator remains the permanent owner. Assigned contest administrators can manage this resource; only the owner or a global administrator can change assignments.') }}</p>
    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <p v-if="busy" role="status">{{ $tr('Updating administrator access…') }}</p>
    <template v-if="data">
      <p>{{ $tr('Owner user ID: {id}', { id: data.owner_user_id }) }}</p>
      <ul>
        <li v-for="item in data.items" :key="item.user_id">
          {{ item.display_name }} ({{ item.username }})
          <button v-if="canEdit" type="button" class="text-button" :disabled="busy" @click="remove(item.user_id)">{{ $tr('Remove access') }}</button>
        </li>
        <li v-if="!data.items.length">{{ $tr('No additional administrators are assigned.') }}</li>
      </ul>
      <form v-if="canEdit" class="inline-form" @submit.prevent="add">
        <label for="resource-admin-user">{{ $tr('Add contest administrator') }}</label>
        <select id="resource-admin-user" v-model="selectedUserId" :disabled="busy || !data.eligible.length" required>
          <option value="" disabled>{{ $tr('Select an account') }}</option>
          <option v-for="candidate in data.eligible" :key="candidate.user_id" :value="String(candidate.user_id)">{{ candidate.display_name }} ({{ candidate.username }})</option>
        </select>
        <button class="secondary-button" type="submit" :disabled="busy || !selectedUserId">{{ $tr('Add administrator') }}</button>
      </form>
    </template>
  </section>
</template>
