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
const draft = ref({ username: '', email: '', display_name: '', password: '', role: 'contest_admin' as 'contest_admin' | 'global_administrator', must_change_password: false })

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
    draft.value = { username: '', email: '', display_name: '', password: '', role: 'contest_admin', must_change_password: false }
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
  <section class="page-card user-admin-card" aria-labelledby="user-admin-heading">
    <h1 id="user-admin-heading">{{ $tr('System user administration') }}</h1>
    <p>{{ $tr('Global administrators can create and manage privileged accounts. Contest admins only manage contests and rulesets they own or have been assigned.') }}</p>
    <p v-if="error" role="alert" class="form-error">{{ $tr(error) }}</p>
    <p v-if="message" role="status">{{ $tr(message) }}</p>
    <form class="stacked-form user-admin-create-form" @submit.prevent="create">
      <h2 class="user-admin-form-heading">{{ $tr('Create account') }}</h2>
      <div class="user-admin-form-grid">
        <label for="new-user-name">{{ $tr('Username') }}<input id="new-user-name" v-model.trim="draft.username" required maxlength="80" /></label>
        <label for="new-user-email">{{ $tr('Email address') }}<input id="new-user-email" v-model.trim="draft.email" type="email" required maxlength="320" /></label>
        <label for="new-user-display">{{ $tr('Display name') }}<input id="new-user-display" v-model.trim="draft.display_name" required maxlength="160" /></label>
        <label for="new-user-password">{{ $tr('Temporary password (at least 12 characters)') }}<input id="new-user-password" v-model="draft.password" type="password" required minlength="12" autocomplete="new-password" /></label>
        <label for="new-user-role">{{ $tr('Role') }}<select id="new-user-role" v-model="draft.role"><option value="contest_admin">{{ $tr('Contest admin') }}</option><option value="global_administrator">{{ $tr('Global administrator') }}</option></select></label>
        <label class="user-admin-force-password" for="new-user-force-password"><input id="new-user-force-password" v-model="draft.must_change_password" type="checkbox" /><span>{{ $tr('Require password change at first sign-in') }}</span></label>
      </div>
      <div class="user-admin-form-actions"><button class="primary-button" type="submit" :disabled="busy">{{ $tr('Create account') }}</button></div>
    </form>
    <section aria-labelledby="user-list-heading">
      <div class="user-admin-section-heading"><h2 id="user-list-heading">{{ $tr('Accounts') }}</h2><form class="user-admin-search" @submit.prevent="load"><label for="user-search">{{ $tr('Search') }}</label><input id="user-search" v-model="search" /><button class="secondary-button" type="submit">{{ $tr('Filter') }}</button></form></div>
      <div class="table-scroll user-admin-table-scroll"><table class="user-admin-table"><colgroup><col class="user-column-username" /><col class="user-column-name" /><col class="user-column-email" /><col class="user-column-role" /><col class="user-column-enabled" /><col class="user-column-actions" /></colgroup><thead><tr><th>{{ $tr('Username') }}</th><th>{{ $tr('Name') }}</th><th>{{ $tr('Email address') }}</th><th>{{ $tr('Role') }}</th><th>{{ $tr('Enabled') }}</th><th>{{ $tr('Actions') }}</th></tr></thead><tbody>
        <tr v-for="user in users" :key="user.id"><td><input v-model="user.username" :aria-label="$tr('Username for {name}', { name: user.display_name })" /></td><td><input v-model="user.display_name" :aria-label="$tr('Display name for {name}', { name: user.username })" /></td><td><input v-model="user.email" type="email" :aria-label="$tr('Email for {name}', { name: user.username })" /></td><td><select v-model="user.role" :aria-label="$tr('Role for {name}', { name: user.username })"><option value="contest_admin">{{ $tr('Contest admin') }}</option><option value="global_administrator">{{ $tr('Global administrator') }}</option></select></td><td><input v-model="user.is_active" type="checkbox" :aria-label="$tr('Account enabled for {name}', { name: user.username })" /></td><td><button class="secondary-button" type="button" :disabled="busy" @click="save(user)">{{ $tr('Save') }}</button></td></tr>
      </tbody></table></div>
    </section>
    <section aria-labelledby="participant-list-heading">
      <h2 id="participant-list-heading">{{ $tr('Registered participant accounts') }}</h2>
      <div class="table-scroll user-admin-table-scroll"><table class="user-admin-table participant-admin-table"><colgroup><col class="participant-column-name" /><col class="participant-column-callsigns" /><col class="participant-column-emails" /><col class="participant-column-password" /><col class="participant-column-enabled" /><col class="participant-column-actions" /></colgroup><thead><tr><th>{{ $tr('Participant') }}</th><th>{{ $tr('Callsigns') }}</th><th>{{ $tr('Email addresses') }}</th><th>{{ $tr('Password account') }}</th><th>{{ $tr('Enabled') }}</th><th>{{ $tr('Actions') }}</th></tr></thead><tbody>
        <tr v-for="participant in participants" :key="participant.id"><td><input v-model="participant.display_name" :aria-label="$tr('Display name for participant {id}', { id: participant.id })" /></td><td>{{ participant.callsigns.join(', ') }}</td><td>{{ participant.emails.map((email) => `${email.email}${email.verified ? '' : ' (unverified)'}`).join(', ') }}</td><td>{{ participant.has_password ? $tr('Yes') : $tr('No') }}</td><td><input v-model="participant.is_active" type="checkbox" :aria-label="$tr('Account enabled for participant {id}', { id: participant.id })" /></td><td><button class="secondary-button" type="button" :disabled="busy" @click="saveParticipant(participant)">{{ $tr('Save') }}</button></td></tr>
      </tbody></table></div>
    </section>
  </section>
</template>

<style scoped>
.user-admin-card {
  width: 100%;
  max-width: none;
  min-width: 0;
}

.user-admin-create-form,
.user-admin-card > section {
  min-width: 0;
}

.user-admin-form-heading {
  margin: 0;
}

.user-admin-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 18rem), 1fr));
  gap: 1rem;
  align-items: end;
}

.user-admin-form-grid label {
  min-width: 0;
  display: grid;
  gap: 0.4rem;
  font-weight: 650;
}

.user-admin-form-grid .user-admin-force-password {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  align-self: end;
  min-height: 2.6rem;
  line-height: 1.35;
}

.user-admin-form-grid input,
.user-admin-form-grid select {
  width: 100%;
  min-width: 0;
}

.user-admin-form-grid .user-admin-force-password input[type='checkbox'] {
  width: 1.125rem;
  height: 1.125rem;
  min-width: 1.125rem;
  flex: 0 0 1.125rem;
  margin: 0;
  padding: 0;
}

.user-admin-form-actions {
  display: flex;
  justify-content: flex-end;
}

.user-admin-section-heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.8rem;
}

.user-admin-section-heading h2,
.user-admin-card section > h2 {
  margin: 0;
}

.user-admin-search {
  display: grid;
  grid-template-columns: auto minmax(min(14rem, 30vw), 1fr) auto;
  align-items: center;
  gap: 0.55rem;
  min-width: min(100%, 26rem);
}

.user-admin-search label {
  font-weight: 650;
}

.user-admin-search input {
  width: 100%;
  min-width: 0;
}

.user-admin-table-scroll {
  width: 100%;
  min-width: 0;
  margin-top: 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
}

.user-admin-table {
  width: 100%;
  min-width: 58rem;
  table-layout: fixed;
  border-collapse: collapse;
}

.user-admin-table th,
.user-admin-table td {
  padding: 0.65rem;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  vertical-align: middle;
  overflow-wrap: anywhere;
}

.user-admin-table th {
  color: var(--color-brand-900);
  background: var(--color-surface-muted);
  font-size: 0.9rem;
}

.user-admin-table tr:last-child td {
  border-bottom: 0;
}

.user-admin-table input:not([type='checkbox']),
.user-admin-table select {
  width: 100%;
  min-width: 0;
}

.user-admin-table input[type='checkbox'] {
  display: block;
  margin-inline: auto;
}

.user-column-username { width: 14%; }
.user-column-name { width: 17%; }
.user-column-email { width: 25%; }
.user-column-role { width: 19%; }
.user-column-enabled { width: 10%; }
.user-column-actions { width: 15%; }

.participant-column-name { width: 17%; }
.participant-column-callsigns { width: 15%; }
.participant-column-emails { width: 29%; }
.participant-column-password { width: 15%; }
.participant-column-enabled { width: 10%; }
.participant-column-actions { width: 14%; }

@media (max-width: 760px) {
  .user-admin-section-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .user-admin-search {
    grid-template-columns: auto minmax(0, 1fr) auto;
    min-width: 0;
  }
}

@media (max-width: 420px) {
  .user-admin-search {
    grid-template-columns: 1fr auto;
  }

  .user-admin-search label {
    grid-column: 1 / -1;
  }
}
</style>
