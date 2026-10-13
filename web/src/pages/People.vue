<script setup>
// People (ADR-0005 item 6): who can sign in, and passwords set by someone allowed to manage users.
import { computed, inject, onMounted, ref } from 'vue'
import { api } from '../api'
import { ago } from '../format'

const ws = inject('workspace')
const rows = ref([])
const error = ref('')
const done = ref('')
const pw = ref({})
const canManage = computed(() => ws.value?.user.permissions.includes('users:manage'))

async function load() {
  try { rows.value = await api('/api/users') } catch (e) { error.value = e.message }
}
async function setPassword(u) {
  error.value = ''; done.value = ''
  try {
    await api('/api/users/password', { method: 'POST', body: { email: u.email, password: pw.value[u.email] || '' } })
    pw.value[u.email] = ''
    done.value = `Password set for ${u.name}. Tell them in person or by phone, not by email.`
    await load()
  } catch (e) { error.value = e.message }
}
onMounted(load)
</script>

<template>
  <h1>People</h1>
  <p class="muted small">The people in the company manifest can sign in, with the roles it gives them. To add someone, change a role
    or stop someone's access, change the manifest and run the upgrade (see the runbook).</p>
  <p v-if="error" class="err">{{ error }}</p>
  <p v-if="done" class="ok">{{ done }}</p>
  <table class="grid">
    <thead><tr><th>Name</th><th>Roles</th><th>Department</th><th>Password</th><th>Last sign-in</th><th v-if="canManage">Set a password</th></tr></thead>
    <tbody><tr v-for="u in rows" :key="u.email" :class="{ muted: !u.active }">
      <td>{{ u.name }}<div class="muted small">{{ u.email }}</div></td>
      <td class="small">{{ u.roles.join(', ') }}</td>
      <td class="small">{{ u.department || '—' }}</td>
      <td class="small"><span v-if="!u.active" class="tag">no access</span>
        <template v-else>{{ u.has_password ? 'set' : 'not set' }}<span v-if="u.locked" class="tag">locked</span></template></td>
      <td class="small">{{ u.last_login ? ago(u.last_login) : 'never' }}</td>
      <td v-if="canManage"><form v-if="u.active && u.email !== ws.user.email" class="row" @submit.prevent="setPassword(u)">
        <input v-model="pw[u.email]" type="password" placeholder="New password" autocomplete="new-password" style="max-width:12rem">
        <button>Set</button></form>
        <RouterLink v-else-if="u.email === ws.user.email" to="/account" class="small">Change yours</RouterLink></td>
    </tr></tbody>
  </table>
  <p class="muted small">Setting a password also unlocks the account and signs the person out everywhere. It is recorded.</p>
</template>
