<script setup>
// People (ADR-0005 item 6): who can sign in, and passwords set by someone allowed to manage users.
import { computed, inject, onMounted, ref } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import PageTop from '../ui/PageTop.vue'
import { api } from '../api'
import { ago } from '../format'
import { t } from '../i18n'

const ws = inject('workspace')
const rows = ref([])
const error = ref('')
const done = ref('')
const pw = ref({})
const canManage = computed(() => ws.value?.user.permissions.includes('users:manage'))
const isOwner = computed(() => ws.value?.user.roles.includes('owner'))
const ROLES = ['owner', 'ops_manager', 'warehouse', 'purchasing', 'sales', 'quality', 'ai_specialist']
const blank = () => ({ name: '', email: '', roles: [], department: '' })
const add = ref(blank())

async function load() {
  try { rows.value = await api('/api/users') } catch (e) { error.value = e.message }
}
async function setPassword(u) {
  error.value = ''; done.value = ''
  try {
    await api('/api/users/password', { method: 'POST', body: { email: u.email, password: pw.value[u.email] || '' } })
    pw.value[u.email] = ''
    done.value = t('Password set for {name}. Tell them in person or by phone, not by email.', { name: u.name })
    await load()
  } catch (e) { error.value = e.message }
}
async function addPerson() {
  error.value = ''; done.value = ''
  try {
    const p = await api('/api/users', { method: 'POST', body: add.value })
    add.value = blank()
    done.value = t('{name} added. Set their password below and tell them in person or by phone.', { name: p.name })
    await load()
  } catch (e) { error.value = e.message }
}
async function removePerson(u) {
  if (!window.confirm(t('Stop the access of {name}? Their records stay.', { name: u.name }))) return
  error.value = ''; done.value = ''
  try {
    await api('/api/users/remove', { method: 'POST', body: { email: u.email } })
    done.value = t('{name} no longer has access.', { name: u.name })
    await load()
  } catch (e) { error.value = e.message }
}
onMounted(load)
</script>

<template>
  <PageTop :title="t('People')" />
  <p class="wq-muted mb-4 max-w-3xl">{{ t('Add colleagues here and set their passwords. People in the company manifest are changed in the manifest (see the runbook).') }}</p>
  <p v-if="error" class="wq-error mb-4">{{ error }}</p>
  <p v-if="done" class="mb-4 rounded-3 border border-outline-green-3 bg-surface-green-2 px-3 py-2 text-base text-ink-green-7">{{ done }}</p>
  <form v-if="canManage" data-help="people-add" class="wq-panel mb-4 flex flex-wrap items-end gap-3 p-4" @submit.prevent="addPerson">
    <label class="flex flex-col gap-1 text-sm">{{ t('Name') }}<input v-model="add.name" class="wq-input w-44" required></label>
    <label class="flex flex-col gap-1 text-sm">{{ t('Email') }}<input v-model="add.email" class="wq-input w-56" type="email" required></label>
    <fieldset class="flex flex-col gap-1 text-sm"><legend class="mb-1">{{ t('Roles') }}</legend>
      <div class="flex flex-wrap gap-x-3 gap-y-1">
        <label v-for="r in ROLES" v-show="r !== 'owner' || isOwner" :key="r" class="flex items-center gap-1 capitalize">
          <input v-model="add.roles" type="checkbox" :value="r">{{ t(r.replace('_', ' ')) }}</label>
      </div></fieldset>
    <label v-if="ws.departments?.length" class="flex flex-col gap-1 text-sm">{{ t('Department') }}
      <select v-model="add.department" class="wq-input w-40"><option value="">—</option>
        <option v-for="d in ws.departments" :key="d.id" :value="d.id">{{ d.name }}</option></select></label>
    <Button type="submit" variant="solid" :label="t('Add person')" />
  </form>
  <div data-help="people-list" class="wq-panel overflow-x-auto">
    <table class="wq-table">
      <thead><tr><th>{{ t('Name') }}</th><th>{{ t('Roles') }}</th><th>{{ t('Department') }}</th><th>{{ t('Password') }}</th><th>{{ t('Last sign-in') }}</th><th v-if="canManage">{{ t('Set a password') }}</th></tr></thead>
      <tbody><tr v-for="u in rows" :key="u.email" :class="{ 'opacity-60': !u.active }">
        <td><div class="flex items-center gap-2.5"><Avatar :label="u.name" size="md" />
          <div><div class="font-medium text-ink-gray-9">{{ u.name }}</div><div class="text-sm text-ink-gray-5">{{ u.email }}</div></div></div></td>
        <td><Badge v-for="r in u.roles" :key="r" :label="t(r.replace('_', ' '))" class="me-1 capitalize" /></td>
        <td class="text-sm capitalize text-ink-gray-6">{{ u.department || '—' }}</td>
        <td class="text-sm"><Badge v-if="!u.active" :label="t('no access')" />
          <template v-else><span :class="u.has_password ? 'text-ink-gray-8' : 'text-ink-gray-5'">{{ u.has_password ? t('set') : t('not set') }}</span>
            <Badge v-if="u.locked" theme="red" :label="t('locked')" class="ms-1" /></template></td>
        <td class="whitespace-nowrap text-sm text-ink-gray-5">{{ u.last_login ? ago(u.last_login) : t('never') }}</td>
        <td v-if="canManage"><form v-if="u.active && u.email !== ws.user.email" data-help="people-set-password" class="flex gap-2" @submit.prevent="setPassword(u)">
          <input v-model="pw[u.email]" class="wq-input w-44" type="password" :placeholder="t('New password')" autocomplete="new-password">
          <Button type="submit" :label="t('Set')" /></form>
          <RouterLink v-else-if="u.email === ws.user.email" to="/account" class="wq-link text-sm">{{ t('Change yours') }}</RouterLink>
          <button v-if="u.active && u.source === 'app' && u.email !== ws.user.email" type="button" class="wq-link mt-1 text-sm" @click="removePerson(u)">{{ t('Remove') }}</button></td>
      </tr></tbody>
    </table>
  </div>
  <p class="wq-muted mt-3">{{ t('Setting a password also unlocks the account and signs the person out everywhere. It is recorded.') }}</p>
</template>
