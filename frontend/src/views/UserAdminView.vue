<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ApiError } from '../api/client'
import { createSystemUser, listSystemUsers, listParticipantAccounts, updateParticipantAccount, updateSystemUser, type ParticipantAccountRecord, type SystemUserRecord } from '../api/identity'

const users = ref<SystemUserRecord[]>([])
const participants = ref<ParticipantAccountRecord[]>([])
const search = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')
const draft = ref({ username: '', email: '', display_name: '', password: '', role: 'contest_admin' as 'contest_admin' | 'global_administrator' })

async function load() {
  busy.value = true
  error.value = ''
  try {
    const [staff, contestants] = await Promise.all([listSystemUsers(search.value), listParticipantAccounts(search.value)])
    users.value = staff.items
    participants.value = contestants.items
  }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'Users could not be loaded.' }
  finally { busy.value = false }
}
async function saveParticipant(participant: ParticipantAccountRecord) {
  busy.value = true
  error.value = ''
  try { Object.assign(participant, await updateParticipantAccount(participant.id, participant)); message.value = 'Participant account changes saved.' }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'Participant changes could not be saved.' }
  finally { busy.value = false }
}
async function create() {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await createSystemUser(draft.value)
    draft.value = { username: '', email: '', display_name: '', password: '', role: 'contest_admin' }
    message.value = 'The account was created.'
    await load()
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'The account could not be created.' }
  finally { busy.value = false }
}
async function save(user: SystemUserRecord) {
  busy.value = true
  error.value = ''
  try { Object.assign(user, await updateSystemUser(user.id, user)); message.value = 'Account changes saved.' }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : 'Account changes could not be saved.' }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <section class="page-card" aria-labelledby="user-admin-heading">
    <h1 id="user-admin-heading">{{ $tr('System user administration') }}</h1>
    <p>{{ $tr('Global administrators can create and manage privileged accounts. Contest admins only manage contests and rulesets they own or have been assigned.') }}</p>
    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <p v-if="message" role="status">{{ $tr(message) }}</p>
    <form class="stacked-form" @submit.prevent="create">
      <h2>{{ $tr('Create account') }}</h2>
      <label for="new-user-name">{{ $tr('Username') }}</label><input id="new-user-name" v-model.trim="draft.username" required maxlength="80" />
      <label for="new-user-email">{{ $tr('Email address') }}</label><input id="new-user-email" v-model.trim="draft.email" type="email" required maxlength="320" />
      <label for="new-user-display">{{ $tr('Display name') }}</label><input id="new-user-display" v-model.trim="draft.display_name" required maxlength="160" />
      <label for="new-user-password">{{ $tr('Temporary password (at least 12 characters)') }}</label><input id="new-user-password" v-model="draft.password" type="password" required minlength="12" autocomplete="new-password" />
      <label for="new-user-role">{{ $tr('Role') }}</label><select id="new-user-role" v-model="draft.role"><option value="contest_admin">{{ $tr('Contest admin') }}</option><option value="global_administrator">{{ $tr('Global administrator') }}</option></select>
      <button class="primary-button" type="submit" :disabled="busy">{{ $tr('Create account') }}</button>
    </form>
    <section aria-labelledby="user-list-heading">
      <div class="section-heading-row"><h2 id="user-list-heading">{{ $tr('Accounts') }}</h2><form class="inline-form" @submit.prevent="load"><label for="user-search">{{ $tr('Search') }}</label><input id="user-search" v-model="search" /><button class="secondary-button" type="submit">{{ $tr('Filter') }}</button></form></div>
      <div class="table-scroll"><table><thead><tr><th>{{ $tr('Username') }}</th><th>{{ $tr('Name') }}</th><th>{{ $tr('Email address') }}</th><th>{{ $tr('Role') }}</th><th>{{ $tr('Enabled') }}</th><th>{{ $tr('Actions') }}</th></tr></thead><tbody>
        <tr v-for="user in users" :key="user.id"><td><input v-model="user.username" :aria-label="$tr('Username for {name}', { name: user.display_name })" /></td><td><input v-model="user.display_name" :aria-label="$tr('Display name for {name}', { name: user.username })" /></td><td><input v-model="user.email" type="email" :aria-label="$tr('Email for {name}', { name: user.username })" /></td><td><select v-model="user.role" :aria-label="$tr('Role for {name}', { name: user.username })"><option value="contest_admin">{{ $tr('Contest admin') }}</option><option value="global_administrator">{{ $tr('Global administrator') }}</option></select></td><td><input v-model="user.is_active" type="checkbox" :aria-label="$tr('Account enabled for {name}', { name: user.username })" /></td><td><button class="secondary-button" type="button" :disabled="busy" @click="save(user)">{{ $tr('Save') }}</button></td></tr>
      </tbody></table></div>
    </section>
    <section aria-labelledby="participant-list-heading">
      <h2 id="participant-list-heading">{{ $tr('Participant accounts') }}</h2>
      <div class="table-scroll"><table><thead><tr><th>{{ $tr('Participant') }}</th><th>{{ $tr('Callsigns') }}</th><th>{{ $tr('Email addresses') }}</th><th>{{ $tr('Password account') }}</th><th>{{ $tr('Enabled') }}</th><th>{{ $tr('Actions') }}</th></tr></thead><tbody>
        <tr v-for="participant in participants" :key="participant.id"><td><input v-model="participant.display_name" :aria-label="$tr('Display name for participant {id}', { id: participant.id })" /></td><td>{{ participant.callsigns.join(', ') }}</td><td>{{ participant.emails.map((email) => `${email.email}${email.verified ? '' : ' (unverified)'}`).join(', ') }}</td><td>{{ participant.has_password ? $tr('Yes') : $tr('No') }}</td><td><input v-model="participant.is_active" type="checkbox" :aria-label="$tr('Account enabled for participant {id}', { id: participant.id })" /></td><td><button class="secondary-button" type="button" :disabled="busy" @click="saveParticipant(participant)">{{ $tr('Save') }}</button></td></tr>
      </tbody></table></div>
    </section>
  </section>
</template>
